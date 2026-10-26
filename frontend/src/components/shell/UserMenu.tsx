import { User } from "lucide-react";
import type { MeOut } from "../../api/me";
import { Menu, menuItemCls } from "./Menu";
import { useSignOut } from "./session";

export function UserMenu({ me }: { me: MeOut }) {
  const signOut = useSignOut();
  const name = me.name ?? me.email ?? `User ${me.id}`;
  return (
    <Menu
      label="User menu"
      trigger={
        <>
          <User className="size-4" aria-hidden />
          <span className="hidden sm:inline">{name}</span>
        </>
      }
    >
      {(close) => (
        <>
          <div className="flex items-center justify-between gap-3 px-2 py-1.5 text-sm">
            <span className="font-medium">{name}</span>
            <span className="rounded bg-secondary px-1.5 py-0.5 text-xs text-secondary-foreground">{me.role}</span>
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
            Sign out
          </button>
        </>
      )}
    </Menu>
  );
}
