import { Monitor, Moon, Sun } from "lucide-react";
import { Menu, menuItemCls } from "./Menu";
import { useTheme, type Theme } from "./theme";

const OPTS: { v: Theme; label: string; icon: typeof Sun }[] = [
  { v: "light", label: "Light", icon: Sun },
  { v: "dark", label: "Dark", icon: Moon },
  { v: "system", label: "System", icon: Monitor },
];

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const Icon = OPTS.find((o) => o.v === theme)?.icon ?? Monitor;
  return (
    <Menu label="Theme" trigger={<Icon className="size-4" aria-hidden />}>
      {(close) =>
        OPTS.map(({ v, label, icon: I }) => (
          <button
            key={v}
            type="button"
            role="menuitemradio"
            aria-checked={theme === v}
            className={menuItemCls}
            onClick={() => {
              setTheme(v);
              close();
            }}
          >
            <I className="size-4" aria-hidden />
            {label}
          </button>
        ))
      }
    </Menu>
  );
}
