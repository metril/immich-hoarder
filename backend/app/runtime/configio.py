"""YAML export/import of admin-visible configuration (settings, targets, credentials, ...)."""

import base64
import binascii
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.sources import build_source
from app.auth.authz import visible_to
from app.auth.principal import Principal
from app.core.crypto import SecretBox, SecretDecryptError
from app.db.models import (
    Credential,
    CredentialKind,
    ImmichTarget,
    Setting,
    Share,
    Source,
    User,
    Visibility,
)
from app.rip.settings import RipSettings, load_rip_settings
from app.runtime.notify import check_notify_url
from app.runtime.settings import (
    NotifySettings,
    RuntimeSettings,
    _apprise_ok,
    load_model,
)
from app.schemas.credentials import CredentialIn
from app.schemas.shares import ShareEntry
from app.schemas.sources import SourceIn
from app.schemas.targets import TargetIn

VERSION = 1
KINDS = ("settings", "targets", "credentials", "sources", "shares")
SETTING_MODELS: dict[str, type[BaseModel]] = {
    "rip": RipSettings,
    "runtime": RuntimeSettings,
    "notify": NotifySettings,
}
SHARE_MODELS: dict[str, Any] = {
    "source": Source,
    "target": ImmichTarget,
    "credential": Credential,
}
# Source columns carried through verbatim (target/credential/notify/proxy are mapped).
SOURCE_PLAIN = (
    "name url album_template schedule_cron backfill_mode backfill_value allow_animated "
    "filters gdl_options log_level enabled visibility"
).split()
SOURCE_KEYS = {*SOURCE_PLAIN, "owner", "target", "credential", "notify", "proxy", "proxy_enc"}


def _enc(box: SecretBox, plain: str) -> str:
    return base64.b64encode(box.encrypt(plain.encode())).decode()


def _has_userinfo(url: str) -> bool:
    try:
        p = urlsplit(url)
        return bool(p.username or p.password)
    except ValueError:
        return True


def _proxy_out(d: dict[str, Any], proxy: str | None, box: SecretBox | None) -> None:
    """Write proxy, moving URLs carrying credentials into `proxy_enc` (or dropping them)."""
    if proxy is None:
        d["proxy"] = None
    elif not _has_userinfo(proxy):
        d["proxy"] = proxy
    elif box is not None:
        d["proxy_enc"] = _enc(box, proxy)


def _dec(box: SecretBox, token: Any) -> str:
    if not isinstance(token, str):
        raise ValueError("invalid encrypted secret")
    try:
        return box.decrypt(base64.b64decode(token, validate=True)).decode()
    except (binascii.Error, UnicodeDecodeError):
        raise ValueError("invalid encrypted secret") from None
    except SecretDecryptError:
        raise ValueError("encrypted secret cannot be decrypted with this master key") from None


# --------------------------------------------------------------------------- export


async def export_config(session: AsyncSession, box: SecretBox | None) -> dict[str, Any]:
    """Build the export document; `box` is given only when secrets are included (encrypted)."""
    subs = {u.id: u.sub for u in (await session.execute(select(User))).scalars()}
    targets = list(
        (await session.execute(select(ImmichTarget).order_by(ImmichTarget.id))).scalars()
    )
    creds = list((await session.execute(select(Credential).order_by(Credential.id))).scalars())
    sources = list(
        (
            await session.execute(
                select(Source).where(Source.ephemeral.is_(False)).order_by(Source.id)
            )
        ).scalars()
    )
    tname = {t.id: t.name for t in targets}
    cname = {c.id: c.name for c in creds}

    rip = (await load_model(session, "rip", RipSettings)).model_dump(mode="json")
    rip_proxy = rip.pop("proxy")
    _proxy_out(rip, rip_proxy, box)
    notify = (await load_model(session, "notify", NotifySettings)).model_dump(mode="json")
    urls = notify.pop("urls")
    if box is not None:
        notify["urls_enc"] = [_enc(box, u) for u in urls]
    settings = {
        "rip": rip,
        "runtime": (await load_model(session, "runtime", RuntimeSettings)).model_dump(mode="json"),
        "notify": notify,
    }

    t_out = []
    for t in targets:
        d: dict[str, Any] = {
            "name": t.name,
            "visibility": t.visibility.value,
            "owner": subs.get(t.owner_id),
        }
        if not _has_userinfo(t.url):
            d["url"] = t.url
        elif box is not None:
            d["url_enc"] = _enc(box, t.url)
        if box is not None:
            d["api_key_enc"] = base64.b64encode(t.api_key_enc).decode()
        t_out.append(d)
    c_out = []
    for c in creds:
        d = {
            "name": c.name,
            "site": c.site,
            "kind": c.kind.value,
            "visibility": c.visibility.value,
            "owner": subs.get(c.owner_id),
        }
        if box is not None:
            d["secret_enc"] = base64.b64encode(c.secret_enc).decode()
        c_out.append(d)
    s_out = []
    for s in sources:
        d = {
            k: (v.value if hasattr(v, "value") else v)
            for k in SOURCE_PLAIN
            for v in [getattr(s, k)]
        }
        d["owner"] = subs.get(s.owner_id)
        d["target"] = tname.get(s.target_id)
        d["credential"] = cname.get(s.credential_id) if s.credential_id is not None else None
        n = dict(s.notify or {})
        ids = n.pop("credential_ids", None) or []
        n["credentials"] = [cname[i] for i in ids if i in cname]
        d["notify"] = n
        _proxy_out(d, s.proxy, box)
        s_out.append(d)

    names: dict[str, dict[int, tuple[str, str | None]]] = {
        "target": {t.id: (t.name, subs.get(t.owner_id)) for t in targets},
        "credential": {c.id: (c.name, subs.get(c.owner_id)) for c in creds},
        "source": {s.id: (s.name, subs.get(s.owner_id)) for s in sources},
    }
    sh_out = []
    for sh in (await session.execute(select(Share).order_by(Share.id))).scalars():
        res = names.get(sh.resource_type, {}).get(sh.resource_id)
        if res is None:
            continue
        sh_out.append(
            {
                "resource_type": sh.resource_type,
                "resource": res[0],
                "owner": res[1],
                "principal_type": sh.principal_type.value,
                "principal_id": sh.principal_id,
                "perm": sh.perm.value,
            }
        )
    return {
        "version": VERSION,
        "settings": settings,
        "targets": t_out,
        "credentials": c_out,
        "sources": s_out,
        "shares": sh_out,
    }


# --------------------------------------------------------------------------- import


@dataclass
class ImportResult:
    created: dict[str, int] = field(default_factory=lambda: dict.fromkeys(KINDS, 0))
    skipped: dict[str, int] = field(default_factory=lambda: dict.fromkeys(KINDS, 0))
    errors: list[str] = field(default_factory=list)
    new_source_ids: list[int] = field(default_factory=list)
    runtime_changed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"created": self.created, "skipped": self.skipped, "errors": self.errors}


class _Abort(Exception):
    pass


def _verr(e: ValidationError) -> str:
    # loc + message only: pydantic inputs may be secrets
    return "; ".join(
        f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()[:5]
    )


class _Importer:
    def __init__(
        self, session: AsyncSession, admin: Principal, box: SecretBox, doc: dict[str, Any]
    ) -> None:
        self.s = session
        self.admin = admin
        self.box = box
        self.doc = doc
        self.res = ImportResult()
        self._users: dict[str, User | None] = {}

    def err(self, where: str, msg: str) -> None:
        self.res.errors.append(f"{where}: {msg}")

    async def _flush(self, where: str) -> None:
        try:
            await self.s.flush()
        except SQLAlchemyError:
            self.err(where, "database error")
            raise _Abort from None

    def _items(self, kind: str) -> list[tuple[int, dict[str, Any]]]:
        raw = self.doc.get(kind)
        if raw is None:
            return []
        if not isinstance(raw, list):
            self.err(kind, "must be a list")
            return []
        out = []
        for i, e in enumerate(raw):
            if isinstance(e, dict):
                out.append((i, e))
            else:
                self.err(f"{kind}[{i}]", "must be a mapping")
        return out

    async def owner(self, entry: dict[str, Any]) -> int:
        sub = entry.get("owner")
        if not isinstance(sub, str) or not sub:
            return self.admin.user_id
        if sub not in self._users:
            self._users[sub] = (
                await self.s.execute(select(User).where(User.sub == sub))
            ).scalar_one_or_none()
        u = self._users[sub]
        return u.id if u else self.admin.user_id

    async def exists(self, model: Any, owner_id: int, name: str) -> bool:
        stmt = select(model.id).where(model.owner_id == owner_id, model.name == name)
        return (await self.s.execute(stmt)).first() is not None

    async def find(self, model: Any, owner_id: int, name: Any) -> Any:
        """Own item first, then any item the owner can use."""
        if not isinstance(name, str):
            return None
        own = (
            (
                await self.s.execute(
                    select(model).where(model.owner_id == owner_id, model.name == name)
                )
            )
            .scalars()
            .first()
        )
        if own is not None:
            return own
        owner = await self.s.get(User, owner_id)
        if owner is None:
            return None
        op = Principal(owner.id, owner.role, frozenset(owner.groups or []), None)
        stmt = visible_to(select(model).where(model.name == name), model, op)
        return (await self.s.execute(stmt.order_by(model.id))).scalars().first()

    def secret(self, e: dict[str, Any], plain: str, enc: str) -> str:
        if enc in e:
            return _dec(self.box, e[enc])
        v = e.get(plain)
        if not isinstance(v, str) or not v:
            raise ValueError(f"missing {plain}")
        return v

    async def run(self) -> ImportResult:
        try:
            await self.settings()
            await self.targets()
            await self.credentials()
            await self.shares(sources=False)
            await self.sources()
            await self.shares(sources=True)
        except _Abort:
            pass
        return self.res

    async def settings(self) -> None:
        raw = self.doc.get("settings")
        if raw is None:
            return
        if not isinstance(raw, dict):
            return self.err("settings", "must be a mapping")
        for key, val in raw.items():
            where = f"settings.{key}"
            model = SETTING_MODELS.get(key) if isinstance(key, str) else None
            if model is None:
                self.err(where if isinstance(key, str) else "settings", "unknown settings key")
                continue
            try:
                data = await self._setting_data(key, val)
                valid = model.model_validate(data).model_dump(mode="json")
            except ValidationError as e:
                self.err(where, _verr(e))
                continue
            except ValueError as e:
                self.err(where, str(e))
                continue
            if await self.s.get(Setting, key) is not None:
                self.res.skipped["settings"] += 1
                continue
            self.s.add(Setting(key=key, value=valid))
            self.res.created["settings"] += 1
            self.res.runtime_changed |= key == "runtime"
            await self._flush(where)

    async def _setting_data(self, key: str, val: Any) -> dict[str, Any]:
        if not isinstance(val, dict):
            raise ValueError("must be a mapping")
        data = dict(val)
        if key == "notify" and "urls_enc" in data:
            enc = data.pop("urls_enc")
            if not isinstance(enc, list):
                raise ValueError("invalid encrypted secret")
            data["urls"] = [_dec(self.box, t) for t in enc]
        if key == "rip" and "proxy_enc" in data:
            data["proxy"] = _dec(self.box, data.pop("proxy_enc"))
        return data

    async def targets(self) -> None:
        for i, e in self._items("targets"):
            where = f"targets[{i}]"
            try:
                owner_id = await self.owner(e)
                name = e.get("name")
                if isinstance(name, str) and await self.exists(ImmichTarget, owner_id, name):
                    self.res.skipped["targets"] += 1
                    continue
                key_enc = self._ciphertext(e, "api_key", "api_key_enc")
                body = TargetIn(
                    name=e.get("name"),
                    url=_dec(self.box, e["url_enc"]) if "url_enc" in e else e.get("url"),
                    api_key="x",
                    visibility=e.get("visibility", Visibility.private),
                )
            except ValidationError as ex:
                self.err(where, _verr(ex))
                continue
            except ValueError as ex:
                self.err(where, str(ex))
                continue
            self.s.add(
                ImmichTarget(
                    name=body.name,
                    url=body.url,
                    api_key_enc=key_enc,
                    owner_id=owner_id,
                    visibility=body.visibility,
                )
            )
            self.res.created["targets"] += 1
            await self._flush(where)

    def _ciphertext(self, e: dict[str, Any], plain: str, enc: str) -> bytes:
        """Return SecretBox ciphertext for an entry's secret (verifying imported tokens)."""
        if enc in e:
            token = e[enc]
            _dec(self.box, token)  # raises if undecryptable under this key
            return base64.b64decode(token)
        return self.box.encrypt(self.secret(e, plain, enc).encode())

    async def credentials(self) -> None:
        rip = None
        for i, e in self._items("credentials"):
            where = f"credentials[{i}]"
            try:
                owner_id = await self.owner(e)
                name = e.get("name")
                if isinstance(name, str) and await self.exists(Credential, owner_id, name):
                    self.res.skipped["credentials"] += 1
                    continue
                secret_enc = self._ciphertext(e, "secret", "secret_enc")
                body = CredentialIn(
                    name=e.get("name"),
                    site=e.get("site"),
                    kind=e.get("kind"),
                    secret="x",
                    visibility=e.get("visibility", Visibility.private),
                )
                if body.kind == CredentialKind.apprise:
                    if rip is None:
                        rip = await load_rip_settings(self.s)
                    plain = self.box.decrypt(secret_enc).decode()
                    check_notify_url(plain, allow_private=rip.allow_private_hosts)
                    if not _apprise_ok(plain):
                        raise ValueError("invalid notification url")
            except ValidationError as ex:
                self.err(where, _verr(ex))
                continue
            except ValueError as ex:
                self.err(where, str(ex))
                continue
            self.s.add(
                Credential(
                    name=body.name,
                    site=body.site,
                    kind=body.kind,
                    secret_enc=secret_enc,
                    owner_id=owner_id,
                    visibility=body.visibility,
                )
            )
            self.res.created["credentials"] += 1
            await self._flush(where)

    async def sources(self) -> None:
        for i, e in self._items("sources"):
            where = f"sources[{i}]"
            try:
                owner_id = await self.owner(e)
                name = e.get("name")
                if isinstance(name, str) and await self.exists(Source, owner_id, name):
                    self.res.skipped["sources"] += 1
                    continue
                if bad := sorted(str(k) for k in e if k not in SOURCE_KEYS):
                    raise ValueError(f"unknown fields: {', '.join(bad)}")
                data = await self._source_data(e, owner_id)
                body = SourceIn.model_validate(data)
                owner = await self.s.get(User, owner_id)
                assert owner is not None
                op = Principal(owner.id, owner.role, frozenset(owner.groups or []), None)
                src = await build_source(self.s, op, body, self.box)
            except ValidationError as ex:
                self.err(where, _verr(ex))
                continue
            except HTTPException as ex:
                self.err(where, str(ex.detail))
                continue
            except ValueError as ex:
                self.err(where, str(ex))
                continue
            self.res.created["sources"] += 1
            self.res.new_source_ids.append(src.id)
            await self._flush(where)

    async def _source_data(self, e: dict[str, Any], owner_id: int) -> dict[str, Any]:
        data: dict[str, Any] = {k: e[k] for k in SOURCE_PLAIN if k in e}
        target = await self.find(ImmichTarget, owner_id, e.get("target"))
        if target is None:
            raise ValueError("unknown target")
        data["target_id"] = target.id
        if e.get("credential") is not None:
            cred = await self.find(Credential, owner_id, e["credential"])
            if cred is None:
                raise ValueError("unknown credential")
            data["credential_id"] = cred.id
        notify = e.get("notify") or {}
        if not isinstance(notify, dict):
            raise ValueError("notify must be a mapping")
        notify = dict(notify)
        refs = notify.pop("credentials", None) or []
        if not isinstance(refs, list):
            raise ValueError("notify.credentials must be a list")
        ids = []
        for ref in refs:
            nc = await self.find(Credential, owner_id, ref)
            if nc is None:
                raise ValueError("unknown notify credential")
            ids.append(nc.id)
        if ids:
            notify["credential_ids"] = ids
        data["notify"] = notify
        if "proxy_enc" in e:
            data["proxy"] = _dec(self.box, e["proxy_enc"])
        elif "proxy" in e:
            data["proxy"] = e["proxy"]
        return data

    async def shares(self, *, sources: bool) -> None:
        """Target/credential shares run before sources (owners may see them only via a
        share); source shares run after. Unknown resource types are reported once."""
        for i, e in self._items("shares"):
            where = f"shares[{i}]"
            known = e.get("resource_type") in SHARE_MODELS
            if known and (e.get("resource_type") == "source") != sources:
                continue
            if not known and sources:
                continue
            try:
                model = SHARE_MODELS.get(str(e.get("resource_type")))
                if model is None:
                    raise ValueError("unknown resource_type")
                entry = ShareEntry.model_validate(
                    {k: e.get(k) for k in ("principal_type", "principal_id", "perm")}
                )
                owner_id = await self.owner(e)
                name = e.get("resource")
                obj = None
                if isinstance(name, str):
                    obj = (
                        (
                            await self.s.execute(
                                select(model).where(model.owner_id == owner_id, model.name == name)
                            )
                        )
                        .scalars()
                        .first()
                    )
                if obj is None:
                    raise ValueError("unknown resource")
            except ValidationError as ex:
                self.err(where, _verr(ex))
                continue
            except ValueError as ex:
                self.err(where, str(ex))
                continue
            dup = await self.s.execute(
                select(Share.id).where(
                    Share.resource_type == model.share_type,
                    Share.resource_id == obj.id,
                    Share.principal_type == entry.principal_type,
                    Share.principal_id == entry.principal_id,
                )
            )
            if dup.first() is not None:
                self.res.skipped["shares"] += 1
                continue
            self.s.add(
                Share(
                    resource_type=model.share_type,
                    resource_id=obj.id,
                    principal_type=entry.principal_type,
                    principal_id=entry.principal_id,
                    perm=entry.perm,
                )
            )
            self.res.created["shares"] += 1
            await self._flush(where)


async def import_config(
    session: AsyncSession, admin: Principal, box: SecretBox, doc: dict[str, Any]
) -> ImportResult:
    return await _Importer(session, admin, box, doc).run()
