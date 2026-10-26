import type { MeOut } from "../../api/me";
import { LogOut } from "lucide-react";
import { Badge } from "../ui/badge";
import { Menu, menuItemCls } from "./Menu";
import { initials } from "./nav";
import { useSignOut } from "./session";

export function UserMenu({ me }: { me: MeOut }) {
  const signOut = useSignOut();
  const name = me.name ?? me.email ?? `User ${me.id}`;
  return (
    <Menu
      label="User menu"
      trigger={
        <span className="grid size-7 place-items-center rounded-full bg-primary/15 text-[11px] font-semibold text-primary" aria-hidden>
          {initials(me)}
        </span>
      }
    >
      {(close) => (
        <>
          <div className="flex items-center justify-between gap-3 px-2 py-1.5 text-sm">
            <span className="font-medium">{name}</span>
            <Badge tone="neutral">{me.role}</Badge>
          </div>
          <button
            type="button"
            role="menuitem"
            className={menuItemCls}
            onClick={() => {
              close();
              void signOut();
            }}
          >
            <LogOut className="size-4" aria-hidden />
            Sign out
          </button>
        </>
      )}
    </Menu>
  );
}
