import { NavLink } from 'react-router-dom';

export function NavBar() {
    return (
        <nav className="nav-bar">
            <NavLink to="/" end className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
                Map
            </NavLink>
            <NavLink to="/profile" className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
                Profile
            </NavLink>
        </nav>
    );
}
