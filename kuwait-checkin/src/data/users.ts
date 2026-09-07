import type { User } from './types';

const avatar = (seed: string) => `https://i.pravatar.cc/150?u=${seed}`;

export const currentUser: User = {
    id: 'user-me',
    name: 'Fahad Al-Sabah',
    username: 'fahad_q8',
    profilePhoto: avatar('fahad_q8'),
    bio: 'Exploring Kuwait one check-in at a time ☕️🇰🇼',
};

export const otherUsers: User[] = [
    {
        id: 'user-mariam',
        name: 'Mariam Al-Fadhli',
        username: 'mariam.f',
        profilePhoto: avatar('mariam.f'),
        bio: 'Coffee first, everything else second.',
    },
    {
        id: 'user-yousef',
        name: 'Yousef Al-Mutairi',
        username: 'yousefm',
        profilePhoto: avatar('yousefm'),
        bio: 'Weekend mall walker.',
    },
    {
        id: 'user-dana',
        name: 'Dana Al-Rashid',
        username: 'dana.r',
        profilePhoto: avatar('dana.r'),
        bio: 'Grocery run, but make it a photo op.',
    },
];

export const users: User[] = [currentUser, ...otherUsers];

export const getUserById = (id: string): User | undefined => users.find(u => u.id === id);
