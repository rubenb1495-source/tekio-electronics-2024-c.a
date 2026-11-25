"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function PaginaDashboardIndice() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/dashboard/ventas/nueva");
  }, [router]);

  return null;
}
