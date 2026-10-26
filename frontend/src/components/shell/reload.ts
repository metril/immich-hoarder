/** Indirection so tests can observe reloads (jsdom's location.reload is not mockable). */
export const pageReload = { reload: () => location.reload() };
