(function () {
  let dark = false;
  try {
    const t = localStorage.getItem("ih-theme") || "system";
    dark = t === "dark" || (t === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  } catch {
    /* storage unavailable: stay light */
  }
  document.documentElement.classList.toggle("dark", dark);
})();
