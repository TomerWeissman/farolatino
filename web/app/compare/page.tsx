import { Suspense } from "react";
import { CompareStub } from "@/components/compare-stub";

// Static export requires Suspense around any client component that
// reads useSearchParams — same pattern as /evaluate.
export default function ComparePage() {
  return (
    <Suspense fallback={null}>
      <CompareStub />
    </Suspense>
  );
}
