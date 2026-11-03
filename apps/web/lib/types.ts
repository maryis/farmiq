export type Risk = {
  id: string;
  cow: string;
  risk_type: string;
  score: number;
  severity: 'high' | 'medium' | 'watch';
  evidence: { message?: string; signal?: string; change_pct?: number }[];
};

export type Dashboard = {
  farm: { id: string; name: string };
  stats: { animals: number; active_alerts: number; high_alerts: number; milk_change_pct: number };
  risks: Risk[];
  inventory: { name: string; stock_kg: number; days_remaining: number; warning: boolean }[];
  feed_opportunity: null | {
    group_id: string;
    group_name: string;
    saving_eur_per_cow_day: number;
    saving_eur_per_month_group: number;
    cost_current_eur_per_cow_day: number;
    cost_recommended_eur_per_cow_day: number;
    items: { name: string; current_kg_dm: number; recommended_kg_dm: number; change_kg_dm: number }[];
  };
};
