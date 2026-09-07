import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Venue } from '../data/types';
import { useAppState } from '../state/AppStateContext';

export function CheckInForm({ venue, onClose }: { venue: Venue; onClose: () => void }) {
    const { addCheckIn } = useAppState();
    const navigate = useNavigate();
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [photoUrl, setPhotoUrl] = useState<string | null>(null);
    const [caption, setCaption] = useState('');
    const [submitted, setSubmitted] = useState(false);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            setPhotoUrl(URL.createObjectURL(file));
        }
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!photoUrl) return;
        addCheckIn({ venueId: venue.id, photoUrl, caption });
        setSubmitted(true);
    };

    const handleDone = () => {
        onClose();
        navigate('/profile');
    };

    return (
        <div className="modal-backdrop" onClick={onClose}>
            <div className="modal" onClick={e => e.stopPropagation()}>
                {submitted ? (
                    <div className="checkin-success">
                        <div className="checkin-success-icon">✅</div>
                        <h3>Checked in at {venue.name}!</h3>
                        <p>Your photo is now on the venue feed, the map, and your profile.</p>
                        <div className="modal-actions">
                            <button className="btn" onClick={onClose}>
                                Stay here
                            </button>
                            <button className="btn btn-primary" onClick={handleDone}>
                                View profile
                            </button>
                        </div>
                    </div>
                ) : (
                    <form onSubmit={handleSubmit}>
                        <h3>Check in at {venue.name}</h3>

                        <label className="photo-drop" htmlFor="checkin-photo">
                            {photoUrl ? (
                                <img src={photoUrl} alt="Selected preview" className="photo-preview" />
                            ) : (
                                <span>📷 Tap to add a photo</span>
                            )}
                        </label>
                        <input
                            id="checkin-photo"
                            ref={fileInputRef}
                            type="file"
                            accept="image/*"
                            capture="environment"
                            onChange={handleFileChange}
                            hidden
                        />

                        <label className="field-label" htmlFor="checkin-caption">
                            Caption (optional)
                        </label>
                        <textarea
                            id="checkin-caption"
                            value={caption}
                            onChange={e => setCaption(e.target.value)}
                            placeholder="How was it?"
                            rows={3}
                            maxLength={280}
                        />

                        <div className="modal-actions">
                            <button type="button" className="btn" onClick={onClose}>
                                Cancel
                            </button>
                            <button type="submit" className="btn btn-primary" disabled={!photoUrl}>
                                Post Check-In
                            </button>
                        </div>
                    </form>
                )}
            </div>
        </div>
    );
}
