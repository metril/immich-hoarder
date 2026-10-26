import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  component: () => <h1 className="p-4 text-lg font-semibold">Immich Hoarder</h1>,
});
