import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { venues } from '../data/venues';
import { categoryMeta } from '../data/categoryMeta';
import { getUserById } from '../data/users';
import { useAppState } from '../state/AppStateContext';
import { CheckInForm } from './CheckInForm';
import { PhotoGrid } from './PhotoGrid';

export function VenueDetail() {
    const { venueId } = useParams<{ venueId: string }>();
    const navigate = useNavigate();
    const { checkIns } = useAppState();
    const [checkInOpen, setCheckInOpen] = useState(false);

    const venue = venues.find(v => v.id === venueId);

    const venueCheckIns = useMemo(
        () =>
            checkIns
                .filter(c => c.venueId === venueId)
                .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()),
        [checkIns, venueId],
    );

    if (!venue) {
        return (
            <div className="page-padded">
                <p>Venue not found.</p>
                <button className="btn" onClick={() => navigate('/')}>
                    Back to map
                </button>
            </div>
        );
    }

    const meta = categoryMeta[venue.category];

    return (
        <div className="venue-detail">
            <button className="back-link" onClick={() => navigate('/')}>
                ← Back to map
            </button>

            <div className="venue-hero" style={{ backgroundImage: `url(${venue.coverPhoto})` }}>
                <div className="venue-hero-overlay">
                    <span className="badge" style={{ background: meta.color }}>
                        {meta.icon} {meta.label}
                    </span>
                    <h1>{venue.name}</h1>
                    <p>{venue.area}, Kuwait</p>
                </div>
            </div>

            <div className="venue-actions">
                <button className="btn btn-primary" onClick={() => setCheckInOpen(true)}>
                    📍 Check In
                </button>
                <span className="checkin-count">
                    {venueCheckIns.length} check-in{venueCheckIns.length === 1 ? '' : 's'}
                </span>
            </div>

            <h2 className="section-title">Photos</h2>
            {venueCheckIns.length === 0 ? (
                <p className="empty-state">No check-ins yet. Be the first to check in here!</p>
            ) : (
                <PhotoGrid
                    items={venueCheckIns.map(c => ({
                        id: c.id,
                        photoUrl: c.photoUrl,
                        caption: c.caption,
                        subtitle: getUserById(c.userId)?.name ?? 'Unknown',
                        timestamp: c.timestamp,
                    }))}
                />
            )}

            {checkInOpen && <CheckInForm venue={venue} onClose={() => setCheckInOpen(false)} />}
        </div>
    );
}
