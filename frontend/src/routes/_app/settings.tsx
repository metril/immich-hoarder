import { createFileRoute } from "@tanstack/react-router";
import { PageSkeleton } from "../../components/common/PageSkeleton";

export const Route = createFileRoute("/_app/settings")({ staticData: { admin: true }, component: PageSkeleton });
