// Сборка статики: HTML/JS из src, шрифты из npm, CSS через Tailwind CLI.
import { execFileSync } from "node:child_process";
import { cpSync, mkdirSync, rmSync } from "node:fs";

rmSync("dist", { recursive: true, force: true });
cpSync("src", "dist", { recursive: true, filter: (p) => !p.includes("/css") });
mkdirSync("dist/assets/fonts", { recursive: true });
for (const family of ["unbounded", "manrope"]) {
  for (const subset of ["latin", "cyrillic"]) {
    const file = `${family}-${subset}-wght-normal.woff2`;
    cpSync(`node_modules/@fontsource-variable/${family}/files/${file}`, `dist/assets/fonts/${file}`);
  }
}
execFileSync("node_modules/.bin/tailwindcss", ["-i", "src/css/app.css", "-o", "dist/assets/app.css", "--minify"], {
  stdio: "inherit",
});
