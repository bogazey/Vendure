import type { VenueCategory } from './types';

export const categoryMeta: Record<VenueCategory, { label: string; color: string; icon: string }> = {
    mall: { label: 'Mall', color: '#7c3aed', icon: '🛍️' },
    coffee_shop: { label: 'Coffee Shop', color: '#b45309', icon: '☕' },
    supermarket: { label: 'Supermarket', color: '#059669', icon: '🛒' },
    store: { label: 'Store', color: '#2563eb', icon: '🏬' },
};
