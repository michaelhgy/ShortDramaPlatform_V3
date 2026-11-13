import type { RevenueCollectorDefinition } from '../api/v2Catalog';

// Names are used only to suggest selections for human confirmation.
// Saved relationships and collection routing always use IDs.
const normalize = (value: string) => value.normalize('NFKC').replace(/[\s·・_-]+/g, '').toLowerCase();
export function suggestRevenueCollectors(name: string, definitions: RevenueCollectorDefinition[]): string[] {
  const key = normalize(name);
  if (!key) return [];
  return definitions.filter(item => item.aliases.some(alias => normalize(alias) === key)).map(item => item.id);
}
