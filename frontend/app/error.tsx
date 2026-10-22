"use client"; // error boundaries must be Client Components
import { ErrorBox } from "@/components/ui";

// a render error in any page: localized message and retry, inside the app shell (the root layout stays mounted)
export default function Error({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return <ErrorBox text="crash" onRetry={retry} />;
}
