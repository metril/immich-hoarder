import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "src/api/schema.d.ts", "src/routeTree.gen.ts", "coverage", "playwright-report", "test-results", ".lighthouseci"] },
  {
    files: ["**/*.{ts,tsx,js,mjs}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommendedTypeChecked, reactHooks.configs.flat.recommended, reactRefresh.configs.vite],
    languageOptions: {
      globals: { ...globals.browser },
      parserOptions: {
        projectService: { allowDefaultProject: ["public/*.js", "*.config.js", "scripts/*.mjs", "e2e/*.ts"] },
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
  {
    files: ["scripts/**/*.mjs", "*.config.{js,ts}"],
    languageOptions: { globals: { ...globals.node } },
  },
  {
    // plain JS outside the TS projects: no type information
    files: ["*.config.js", "public/**/*.js"],
    extends: [tseslint.configs.disableTypeChecked],
  },
  {
    // untyped JS build scripts
    files: ["scripts/**/*.mjs"],
    rules: {
      "@typescript-eslint/no-unsafe-argument": "off",
      "@typescript-eslint/no-unsafe-assignment": "off",
      "@typescript-eslint/no-unsafe-call": "off",
      "@typescript-eslint/no-unsafe-member-access": "off",
      "@typescript-eslint/no-unsafe-return": "off",
    },
  },
  {
    // shadcn primitives export variants alongside components
    files: ["src/components/ui/**"],
    rules: { "react-refresh/only-export-components": "off" },
  },
  {
    // TanStack Router routes throw redirect() objects and export Route next to components
    files: ["src/routes/**"],
    rules: { "@typescript-eslint/only-throw-error": "off", "react-refresh/only-export-components": "off" },
  },
);
