import { Suspense } from "react";
import { CompareDashboard } from "@/components/compare-dashboard";

// Static export requires Suspense around any client component that
// reads useSearchParams — same pattern as /evaluate.
export default function ComparePage() {
  return (
    <Suspense fallback={null}>
      <CompareDashboard />
    </Suspense>
  );
}
