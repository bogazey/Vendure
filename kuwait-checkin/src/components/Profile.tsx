import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { currentUser } from '../data/users';
import { venues } from '../data/venues';
import { categoryMeta } from '../data/categoryMeta';
import { useAppState } from '../state/AppStateContext';
import { PhotoGrid } from './PhotoGrid';

export function Profile() {
    const { checkIns } = useAppState();
    const navigate = useNavigate();

    const myCheckIns = useMemo(
        () =>
            checkIns
                .filter(c => c.userId === currentUser.id)
                .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()),
        [checkIns],
    );

    const placesVisited = useMemo(() => {
        const byVenue = new Map<string, { count: number; latestPhoto: string; latestTimestamp: string }>();
        for (const c of myCheckIns) {
            const existing = byVenue.get(c.venueId);
            if (existing) {
                existing.count += 1;
            } else {
                byVenue.set(c.venueId, { count: 1, latestPhoto: c.photoUrl, latestTimestamp: c.timestamp });
            }
        }
        return Array.from(byVenue.entries())
            .map(([venueId, info]) => ({ venue: venues.find(v => v.id === venueId), ...info }))
            .filter((entry): entry is typeof entry & { venue: NonNullable<typeof entry.venue> } => !!entry.venue)
            .sort((a, b) => new Date(b.latestTimestamp).getTime() - new Date(a.latestTimestamp).getTime());
    }, [myCheckIns]);

    return (
        <div className="profile-page">
            <div className="profile-header">
                <img src={currentUser.profilePhoto} alt={currentUser.name} className="profile-avatar" />
                <div>
                    <h1>{currentUser.name}</h1>
                    <p className="profile-username">@{currentUser.username}</p>
                    <p className="profile-bio">{currentUser.bio}</p>
                </div>
            </div>

            <div className="profile-stats">
                <div className="stat">
                    <div className="stat-value">{myCheckIns.length}</div>
                    <div className="stat-label">Check-ins</div>
                </div>
                <div className="stat">
                    <div className="stat-value">{placesVisited.length}</div>
                    <div className="stat-label">Places</div>
                </div>
            </div>

            <h2 className="section-title">Places visited</h2>
            {placesVisited.length === 0 ? (
                <p className="empty-state">No places visited yet. Check in somewhere on the map!</p>
            ) : (
                <div className="places-list">
                    {placesVisited.map(({ venue, count, latestPhoto }) => {
                        const meta = categoryMeta[venue.category];
                        return (
                            <button
                                key={venue.id}
                                className="place-stamp"
                                onClick={() => navigate(`/venue/${venue.id}`)}
                            >
                                <img src={latestPhoto} alt={venue.name} className="place-stamp-photo" />
                                <div className="place-stamp-info">
                                    <div className="place-stamp-name">
                                        {meta.icon} {venue.name}
                                    </div>
                                    <div className="place-stamp-meta">{venue.area}</div>
                                </div>
                                <div className="place-stamp-count">×{count}</div>
                            </button>
                        );
                    })}
                </div>
            )}

            <h2 className="section-title">My check-ins</h2>
            {myCheckIns.length === 0 ? (
                <p className="empty-state">Your check-in photos will show up here.</p>
            ) : (
                <PhotoGrid
                    items={myCheckIns.map(c => ({
                        id: c.id,
                        photoUrl: c.photoUrl,
                        caption: c.caption,
                        subtitle: venues.find(v => v.id === c.venueId)?.name ?? 'Unknown venue',
                        timestamp: c.timestamp,
                    }))}
                />
            )}
        </div>
    );
}
