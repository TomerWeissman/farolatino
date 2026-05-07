import { Suspense } from "react";
import { Evaluate } from "@/components/evaluate";

// Suspense boundary required for useSearchParams() in Next.js static
// export. Without it, prerendering fails with
// "useSearchParams() should be wrapped in a suspense boundary".
export default function EvaluatePage() {
  return (
    <Suspense fallback={null}>
      <Evaluate />
    </Suspense>
  );
}
