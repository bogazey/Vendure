/*
 * YOUR COLLECTION — this is the only file you need to edit.
 *
 * Each section is one row on the home screen. Each item is one tile.
 *
 *   title  Name shown under the tile.
 *   type   'channel'  -> id is a YouTube channel ID (starts with "UC", 24 characters)
 *          'playlist' -> id is a YouTube playlist ID (starts with "PL", "UU", "OL"...)
 *   id     The channel or playlist ID (see README.md for how to find it).
 *   note   Optional short description shown on the episodes screen.
 *   image  Optional picture URL for the tile. Without it the tile shows the initials.
 *
 * Opening a tile lists its latest episodes; picking one opens it in the YouTube app.
 *
 * Every ID below was checked against YouTube's feed when the list was put together.
 */
var COLLECTION = [
    {
        title: 'Podcasts',
        items: [
            { title: 'Lex Fridman Podcast', type: 'channel', id: 'UCSHZKyawb77ixDdsGog4iWA', note: 'Long, deep conversations with scientists, founders and historians.' },
            { title: 'The Diary Of A CEO', type: 'channel', id: 'UCGq-a57w-aPwyi3pW7XLiHw', note: 'Steven Bartlett interviews founders, doctors and experts.' },
            { title: 'Huberman Lab', type: 'channel', id: 'UC2D2CMWXMOVWx7giW1n3LIg', note: 'Neuroscience and health, explained in practical terms.' },
            { title: 'Dwarkesh Podcast', type: 'channel', id: 'UCXl4i9dYBrFOabk0xGmbkRA', note: 'Exceptionally well-researched interviews on AI, history and progress.' },
            { title: 'Modern Wisdom', type: 'channel', id: 'UCIaH-gZIVC432YRjNVvnyCA', note: 'Chris Williamson on psychology, performance and human nature.' },
            { title: 'All-In Podcast', type: 'channel', id: 'UCESLZhusAkFfsNsApnjF_Cg', note: 'Four investors on tech, markets and politics, weekly.' },
            { title: 'The Tim Ferriss Show', type: 'channel', id: 'UCznv7Vf9nBdJYvBagFdAHWw', note: 'Habits and tactics of world-class performers.' },
            { title: 'The Peter Attia Drive', type: 'channel', id: 'UC8kGsMa0LygSX9nkBcBH1Sg', note: 'Longevity and medicine, in depth.' },
            { title: 'The Rich Roll Podcast', type: 'channel', id: 'UCpjlh0e319ksmoOD7bQFSiw', note: 'Wellness, endurance and personal change.' },
            { title: 'My First Million', type: 'channel', id: 'UCyaN6mg5u8Cjy2ZI4ikWaug', note: 'Business ideas and the stories behind them.' },
            { title: 'Colin and Samir', type: 'channel', id: 'UCamLstJyCa-t5gfZegxsFMw', note: 'The creator economy, from the inside.' },
            { title: 'Conan O\'Brien (Team Coco)', type: 'channel', id: 'UCi7GJNg51C3jgmYTUwqoUXA', note: 'Conan O\'Brien Needs a Friend and classic Conan clips.' },
            { title: 'This Past Weekend', type: 'channel', id: 'UC5AQEUAwCh1sGDvkQtkDWUQ', note: 'Theo Von\'s comedy interviews.' },
            { title: 'The Joe Rogan Experience', type: 'channel', id: 'UCzQUP1qoWDoEbmsQxvdjxgQ', note: 'Long-form interviews with a huge range of guests.' }
        ]
    },
    {
        title: 'TV Shows',
        items: [
            { title: 'Last Week Tonight', type: 'channel', id: 'UC3XTzVzaHQEd30rQbuvCtTQ', note: 'John Oliver\'s weekly deep dive into one big story.' },
            { title: 'The Daily Show', type: 'channel', id: 'UCwWhs_6x42TyRM4Wstoq8HA', note: 'Daily news satire.' },
            { title: 'The Late Show', type: 'channel', id: 'UCMtFAi84ehTSYSE9XoHefig', note: 'With Stephen Colbert.' },
            { title: 'The Tonight Show', type: 'channel', id: 'UC8-Th83bH_thdKZDJCrn88g', note: 'Starring Jimmy Fallon: games, music and guests.' },
            { title: 'Jimmy Kimmel Live', type: 'channel', id: 'UCa6vGFO9ty8v5KZJXQxdhaw', note: 'Monologues, interviews and Mean Tweets.' },
            { title: 'Late Night with Seth Meyers', type: 'channel', id: 'UCVTyTA7-g9nopHeHbeuvpRA', note: 'Home of "A Closer Look".' },
            { title: 'Saturday Night Live', type: 'channel', id: 'UCqFzWxSCi39LnW1JKFR3efg', note: 'Sketches, cold opens and Weekend Update.' },
            { title: 'Taskmaster', type: 'channel', id: 'UCT5C7yaO3RVuOgwP8JVAujQ', note: 'Full episodes of the British comedy game show.' },
            { title: 'Key & Peele', type: 'channel', id: 'UCdN4aXTrHAtfgbVG9HjBmxQ', note: 'Classic sketches.' },
            { title: 'Top Gear', type: 'channel', id: 'UCjOl2AUblVmg2rA_cRgZkFg', note: 'Cars, challenges and road trips.' },
            { title: 'Hot Ones', type: 'channel', id: 'UCPD_bxCRGpmmeQcbe2kpPaA', note: 'Celebrity interviews over increasingly spicy wings.' },
            { title: 'Good Mythical Morning', type: 'channel', id: 'UC4PooiX37Pld1T8J5SYT-SQ', note: 'Rhett and Link\'s daily show.' },
            { title: '60 Minutes', type: 'channel', id: 'UCsN32BtMd0IoByjJRNF12cw', note: 'Investigations and interviews from CBS News.' }
        ]
    },
    {
        title: 'Documentaries',
        items: [
            { title: 'DW Documentary', type: 'channel', id: 'UCW39zufHfsuGgpLviKh297Q', note: 'Full-length documentaries from around the world.' },
            { title: 'FRONTLINE PBS', type: 'channel', id: 'UC3ScyryU9Oy9Wse3a8OAmYQ', note: 'Award-winning investigative films, free in full.' },
            { title: 'BBC Earth', type: 'channel', id: 'UCwmZiChSryoWQCZMIQezgTg', note: 'Nature and wildlife from the BBC.' },
            { title: 'National Geographic', type: 'channel', id: 'UCpVm7bg6pXKo1Pr6k5kxG9A', note: 'Science, exploration and adventure.' },
            { title: 'Free Documentary', type: 'channel', id: 'UCijcd0GR0fkxCAZwkiuWqtQ', note: 'Full documentaries on nature, travel and engineering.' },
            { title: 'Real Stories', type: 'channel', id: 'UCu4XcDBdnZkV6-5z2f16M0g', note: 'Human-interest documentaries.' },
            { title: 'Timeline', type: 'channel', id: 'UC88lvyJe7aHZmcvzvubDFRg', note: 'World history documentaries.' },
            { title: 'LEMMiNO', type: 'channel', id: 'UCRcgy6GzDeccI7dkbbBna3Q', note: 'Meticulous films on mysteries and history.' },
            { title: 'Johnny Harris', type: 'channel', id: 'UCmGSJVG3mCRXVOP4yZrU1Dw', note: 'Visual journalism on geopolitics and maps.' },
            { title: 'Vox', type: 'channel', id: 'UCLXo7UDZvByw2ixzpQCufnA', note: 'Explainers on news, culture and science.' },
            { title: 'VICE', type: 'channel', id: 'UCn8zNIfYAQNdrFRrr8oibKw', note: 'On-the-ground reporting and culture.' },
            { title: 'Al Jazeera English', type: 'channel', id: 'UCNye-wNBqNL5ZzHSJj3l8Bg', note: 'International news and documentaries.' }
        ]
    },
    {
        title: 'Science & Learning',
        items: [
            { title: 'Kurzgesagt', type: 'channel', id: 'UCsXVk37bltHxD1rDPwtNM8Q', note: 'Beautifully animated explainers about science and life.' },
            { title: 'Veritasium', type: 'channel', id: 'UCHnyfMqiRRG1u-2MsSQLbXA', note: 'Science and engineering stories, deeply researched.' },
            { title: '3Blue1Brown', type: 'channel', id: 'UCYO_jab_esuFRV4b17AJtAw', note: 'Maths made visual.' },
            { title: 'Mark Rober', type: 'channel', id: 'UCY1kMZp36IQSyNx_9h4mpCg', note: 'Engineering builds and experiments.' },
            { title: 'SmarterEveryDay', type: 'channel', id: 'UC6107grRI4m0o2-emgoDnAA', note: 'Destin explores how things work.' },
            { title: 'Vsauce', type: 'channel', id: 'UC6nSFpj9HTCZ5t-N3Rm3-HA', note: 'Curious questions, surprising answers.' },
            { title: 'Steve Mould', type: 'channel', id: 'UCEIwxahdLz7bap-VDs9h35A', note: 'Physics you can see on a desk.' },
            { title: 'Tom Scott', type: 'channel', id: 'UCBa659QWEk1AI4Tg--mrJ2A', note: 'Amazing places and things you might not know.' },
            { title: 'Numberphile', type: 'channel', id: 'UCoxcjq-8xIDTYp3uz647V5A', note: 'Mathematicians on numbers.' },
            { title: 'PBS Space Time', type: 'channel', id: 'UC7_gcs09iThXybpVgjHZ_7g', note: 'Astrophysics, taken seriously.' },
            { title: 'OverSimplified', type: 'channel', id: 'UCNIuvl7V8zACPpTmmNIqP2A', note: 'History, animated and funny.' },
            { title: 'CrashCourse', type: 'channel', id: 'UCX6b17PVsYBQ0ip5gyeme-Q', note: 'Whole courses in short episodes.' },
            { title: 'TED', type: 'channel', id: 'UCAuUUnT6oDeKwE6v1NGQxug', note: 'Talks worth watching.' },
            { title: 'NASA', type: 'channel', id: 'UCLA_DiR1FfKNvjuUpBHmylQ', note: 'Launches, missions and live coverage.' },
            { title: 'Primitive Technology', type: 'channel', id: 'UCAL3JXZSzSm8AlZyD3nQdBA', note: 'Building from scratch in the wild, no talking.' }
        ]
    },
    {
        title: 'Tech & Engineering',
        items: [
            { title: 'Marques Brownlee', type: 'channel', id: 'UCBJycsmduvYEL83R_U4JriQ', note: 'The benchmark for tech reviews.' },
            { title: 'Mrwhosetheboss', type: 'channel', id: 'UCMiJRAwDNSNzuYeN2uWa0pA', note: 'Phones and gadgets, tested.' },
            { title: 'Linus Tech Tips', type: 'channel', id: 'UCXuqSBlHAE6Xw-yeJA0Tunw', note: 'PC hardware and builds.' },
            { title: 'The Verge', type: 'channel', id: 'UCddiUEpeqJcYeBxX1IVBKvQ', note: 'Tech news and reviews.' },
            { title: 'ColdFusion', type: 'channel', id: 'UC4QZ_LsYcvcq7qOsOhpAX4A', note: 'Stories of technology and business.' },
            { title: 'Fireship', type: 'channel', id: 'UCsBjURrPoezykLs9EqgamOA', note: 'Fast, funny software news.' },
            { title: 'Two Minute Papers', type: 'channel', id: 'UCbfYPyITQ-7l4upoX8nvctg', note: 'AI research, explained briefly.' },
            { title: 'Computerphile', type: 'channel', id: 'UC9-y-6csu5WGm29I7JiwpnA', note: 'Computer science explained by academics.' },
            { title: 'Real Engineering', type: 'channel', id: 'UCR1IuLEqb6UEA_zQ81kwXfg', note: 'How great machines are engineered.' },
            { title: 'Practical Engineering', type: 'channel', id: 'UCMOqf8ab-42UUQIdVoKwjlQ', note: 'Civil engineering with models.' },
            { title: 'Wendover Productions', type: 'channel', id: 'UC9RM-iSvTu1uPJb8X5yp3EQ', note: 'Logistics, economics and how the world works.' }
        ]
    },
    {
        title: 'Food & Travel',
        items: [
            { title: 'Gordon Ramsay', type: 'channel', id: 'UCIEv3lZ_tNXHzL3ox-_uUGQ', note: 'Recipes and the best of his shows.' },
            { title: 'Bon Appétit', type: 'channel', id: 'UCbpMy0Fg74eXXkvxJrtEn3w', note: 'Test-kitchen cooking.' },
            { title: 'Binging with Babish', type: 'channel', id: 'UCJHA_jMfCvEnv-3kRjTCQXw', note: 'Dishes from films and TV, recreated.' },
            { title: 'Joshua Weissman', type: 'channel', id: 'UChBEbMKI1eCcejTtmI32UEw', note: 'Homemade versions of everything.' },
            { title: 'Mark Wiens', type: 'channel', id: 'UCyEd6QBSgat5kkC6svyjudA', note: 'Street food around the world.' },
            { title: 'Best Ever Food Review Show', type: 'channel', id: 'UCcAd5Np7fO8SeejB1FVKcYw', note: 'Adventurous food travel.' },
            { title: 'Rick Steves\' Europe', type: 'channel', id: 'UCchgIh8Tc4sTmBfnMQ5pDdg', note: 'Full travel episodes across Europe.' },
            { title: 'Kara and Nate', type: 'channel', id: 'UC4ijq8Cg-8zQKx8OH12dUSw', note: 'Travel adventures.' },
            { title: 'Yes Theory', type: 'channel', id: 'UCvK4bOhULCpmLabd2pDMtnA', note: 'Seeking discomfort around the world.' }
        ]
    }
];
