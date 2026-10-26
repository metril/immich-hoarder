import { DropdownMenu } from "radix-ui";
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
    <Menu label="Theme" trigger={<Icon className="size-[18px]" aria-hidden />}>
      <DropdownMenu.RadioGroup value={theme} onValueChange={(v) => setTheme(v as Theme)}>
        {OPTS.map(({ v, label, icon: I }) => (
          <DropdownMenu.RadioItem key={v} value={v} className={menuItemCls}>
            <I className="size-4" aria-hidden />
            {label}
          </DropdownMenu.RadioItem>
        ))}
      </DropdownMenu.RadioGroup>
    </Menu>
  );
}
