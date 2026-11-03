'use client';
import { useEffect, useState } from 'react';
import { getDemoFarm } from '@/lib/api';

export function useDemoFarm() {
  const [farmId, setFarmId] = useState<string>();
  const [error, setError] = useState<string>();
  useEffect(() => { getDemoFarm().then((d) => setFarmId(d.farm_id)).catch((e) => setError(String(e))); }, []);
  return { farmId, error };
}
