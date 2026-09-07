import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import { useNavigate } from 'react-router-dom';
import { venues } from '../data/venues';
import { categoryMeta } from '../data/categoryMeta';
import { useAppState } from '../state/AppStateContext';

const KUWAIT_CENTER: [number, number] = [29.27, 47.99];

function makeIcon(color: string, icon: string, pulsing: boolean) {
    return L.divIcon({
        className: 'venue-marker-wrapper',
        html: `
            <div class="venue-marker ${pulsing ? 'venue-marker--pulsing' : ''}" style="--marker-color:${color}">
                <span class="venue-marker-icon">${icon}</span>
            </div>
        `,
        iconSize: [34, 34],
        iconAnchor: [17, 17],
        popupAnchor: [0, -17],
    });
}

export function MapView() {
    const navigate = useNavigate();
    const { justCheckedInVenueId } = useAppState();

    return (
        <div className="map-page">
            <MapContainer center={KUWAIT_CENTER} zoom={11} scrollWheelZoom className="leaflet-container">
                <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />
                {venues.map(venue => {
                    const meta = categoryMeta[venue.category];
                    const pulsing = justCheckedInVenueId === venue.id;
                    return (
                        <Marker
                            key={venue.id}
                            position={[venue.lat, venue.lng]}
                            icon={makeIcon(meta.color, meta.icon, pulsing)}
                        >
                            <Popup>
                                <div className="map-popup">
                                    <strong>{venue.name}</strong>
                                    <div className="map-popup-meta">
                                        {meta.icon} {meta.label} &middot; {venue.area}
                                    </div>
                                    <button className="btn btn-small" onClick={() => navigate(`/venue/${venue.id}`)}>
                                        View Venue
                                    </button>
                                </div>
                            </Popup>
                        </Marker>
                    );
                })}
            </MapContainer>
            <div className="map-legend">
                {Object.entries(categoryMeta).map(([key, meta]) => (
                    <div className="legend-item" key={key}>
                        <span className="legend-dot" style={{ background: meta.color }} />
                        {meta.icon} {meta.label}
                    </div>
                ))}
            </div>
        </div>
    );
}
