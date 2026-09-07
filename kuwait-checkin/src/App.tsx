import { HashRouter, Routes, Route } from 'react-router-dom';
import { AppStateProvider } from './state/AppStateContext';
import { NavBar } from './components/NavBar';
import { MapView } from './components/MapView';
import { VenueDetail } from './components/VenueDetail';
import { Profile } from './components/Profile';

export default function App() {
    return (
        <AppStateProvider>
            <HashRouter>
                <div className="app-shell">
                    <header className="app-header">
                        <span className="app-title">🇰🇼 Kuwait Check-In</span>
                        <NavBar />
                    </header>
                    <main className="app-main">
                        <Routes>
                            <Route path="/" element={<MapView />} />
                            <Route path="/venue/:venueId" element={<VenueDetail />} />
                            <Route path="/profile" element={<Profile />} />
                        </Routes>
                    </main>
                </div>
            </HashRouter>
        </AppStateProvider>
    );
}
