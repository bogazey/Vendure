import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import type { CheckIn } from '../data/types';
import { seedCheckIns } from '../data/checkins';
import { currentUser } from '../data/users';

interface AppState {
    checkIns: CheckIn[];
    addCheckIn: (input: { venueId: string; photoUrl: string; caption?: string }) => CheckIn;
    /** venueId -> timestamp of the most recently added check-in, used to trigger a pulse on the map */
    justCheckedInVenueId: string | null;
}

const AppStateContext = createContext<AppState | undefined>(undefined);

let nextId = 1;

export function AppStateProvider({ children }: { children: ReactNode }) {
    const [checkIns, setCheckIns] = useState<CheckIn[]>(seedCheckIns);
    const [justCheckedInVenueId, setJustCheckedInVenueId] = useState<string | null>(null);

    const addCheckIn: AppState['addCheckIn'] = ({ venueId, photoUrl, caption }) => {
        const newCheckIn: CheckIn = {
            id: `checkin-${Date.now()}-${nextId++}`,
            userId: currentUser.id,
            venueId,
            photoUrl,
            caption: caption?.trim() ? caption.trim() : undefined,
            timestamp: new Date().toISOString(),
        };
        setCheckIns(prev => [newCheckIn, ...prev]);
        setJustCheckedInVenueId(venueId);
        window.setTimeout(() => {
            setJustCheckedInVenueId(current => (current === venueId ? null : current));
        }, 4000);
        return newCheckIn;
    };

    const value = useMemo(
        () => ({ checkIns, addCheckIn, justCheckedInVenueId }),
        [checkIns, justCheckedInVenueId],
    );

    return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState(): AppState {
    const ctx = useContext(AppStateContext);
    if (!ctx) {
        throw new Error('useAppState must be used within an AppStateProvider');
    }
    return ctx;
}
