import { HoldingsView } from "@/components/HoldingsView";

export default function HoldingsPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">보유종목</h1>
      <HoldingsView />
    </div>
  );
}
