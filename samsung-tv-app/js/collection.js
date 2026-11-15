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
 *   image  Optional logo for the tile: a file in images/logos/ or a web address.
 *          Without it the tile shows the initials.
 *
 * Opening a tile lists its latest episodes; picking one opens it in the YouTube app.
 *
 * Every ID below was checked against YouTube's feed when the list was put together.
 */
var COLLECTION = [
    {
        title: 'Podcasts',
        items: [
            { title: 'Lex Fridman Podcast', type: 'channel', id: 'UCSHZKyawb77ixDdsGog4iWA', image: 'images/logos/UCSHZKyawb77ixDdsGog4iWA.jpg', note: 'Long, deep conversations with scientists, founders and historians.' },
            { title: 'The Diary Of A CEO', type: 'channel', id: 'UCGq-a57w-aPwyi3pW7XLiHw', image: 'images/logos/UCGq-a57w-aPwyi3pW7XLiHw.jpg', note: 'Steven Bartlett interviews founders, doctors and experts.' },
            { title: 'Huberman Lab', type: 'channel', id: 'UC2D2CMWXMOVWx7giW1n3LIg', image: 'images/logos/UC2D2CMWXMOVWx7giW1n3LIg.jpg', note: 'Neuroscience and health, explained in practical terms.' },
            { title: 'Dwarkesh Podcast', type: 'channel', id: 'UCXl4i9dYBrFOabk0xGmbkRA', image: 'images/logos/UCXl4i9dYBrFOabk0xGmbkRA.jpg', note: 'Exceptionally well-researched interviews on AI, history and progress.' },
            { title: 'Modern Wisdom', type: 'channel', id: 'UCIaH-gZIVC432YRjNVvnyCA', image: 'images/logos/UCIaH-gZIVC432YRjNVvnyCA.jpg', note: 'Chris Williamson on psychology, performance and human nature.' },
            { title: 'All-In Podcast', type: 'channel', id: 'UCESLZhusAkFfsNsApnjF_Cg', image: 'images/logos/UCESLZhusAkFfsNsApnjF_Cg.jpg', note: 'Four investors on tech, markets and politics, weekly.' },
            { title: 'The Tim Ferriss Show', type: 'channel', id: 'UCznv7Vf9nBdJYvBagFdAHWw', image: 'images/logos/UCznv7Vf9nBdJYvBagFdAHWw.jpg', note: 'Habits and tactics of world-class performers.' },
            { title: 'The Peter Attia Drive', type: 'channel', id: 'UC8kGsMa0LygSX9nkBcBH1Sg', image: 'images/logos/UC8kGsMa0LygSX9nkBcBH1Sg.jpg', note: 'Longevity and medicine, in depth.' },
            { title: 'The Rich Roll Podcast', type: 'channel', id: 'UCpjlh0e319ksmoOD7bQFSiw', image: 'images/logos/UCpjlh0e319ksmoOD7bQFSiw.jpg', note: 'Wellness, endurance and personal change.' },
            { title: 'My First Million', type: 'channel', id: 'UCyaN6mg5u8Cjy2ZI4ikWaug', image: 'images/logos/UCyaN6mg5u8Cjy2ZI4ikWaug.jpg', note: 'Business ideas and the stories behind them.' },
            { title: 'Colin and Samir', type: 'channel', id: 'UCamLstJyCa-t5gfZegxsFMw', image: 'images/logos/UCamLstJyCa-t5gfZegxsFMw.jpg', note: 'The creator economy, from the inside.' },
            { title: 'Conan O\'Brien (Team Coco)', type: 'channel', id: 'UCi7GJNg51C3jgmYTUwqoUXA', image: 'images/logos/UCi7GJNg51C3jgmYTUwqoUXA.jpg', note: 'Conan O\'Brien Needs a Friend and classic Conan clips.' },
            { title: 'This Past Weekend', type: 'channel', id: 'UC5AQEUAwCh1sGDvkQtkDWUQ', image: 'images/logos/UC5AQEUAwCh1sGDvkQtkDWUQ.jpg', note: 'Theo Von\'s comedy interviews.' },
            { title: 'The Joe Rogan Experience', type: 'channel', id: 'UCzQUP1qoWDoEbmsQxvdjxgQ', image: 'images/logos/UCzQUP1qoWDoEbmsQxvdjxgQ.jpg', note: 'Long-form interviews with a huge range of guests.' }
        ]
    },
    {
        title: 'TV Shows',
        items: [
            { title: 'Last Week Tonight', type: 'channel', id: 'UC3XTzVzaHQEd30rQbuvCtTQ', image: 'images/logos/UC3XTzVzaHQEd30rQbuvCtTQ.jpg', note: 'John Oliver\'s weekly deep dive into one big story.' },
            { title: 'The Daily Show', type: 'channel', id: 'UCwWhs_6x42TyRM4Wstoq8HA', image: 'images/logos/UCwWhs_6x42TyRM4Wstoq8HA.jpg', note: 'Daily news satire.' },
            { title: 'The Late Show', type: 'channel', id: 'UCMtFAi84ehTSYSE9XoHefig', image: 'images/logos/UCMtFAi84ehTSYSE9XoHefig.jpg', note: 'With Stephen Colbert.' },
            { title: 'The Tonight Show', type: 'channel', id: 'UC8-Th83bH_thdKZDJCrn88g', image: 'images/logos/UC8-Th83bH_thdKZDJCrn88g.jpg', note: 'Starring Jimmy Fallon: games, music and guests.' },
            { title: 'Jimmy Kimmel Live', type: 'channel', id: 'UCa6vGFO9ty8v5KZJXQxdhaw', image: 'images/logos/UCa6vGFO9ty8v5KZJXQxdhaw.jpg', note: 'Monologues, interviews and Mean Tweets.' },
            { title: 'Late Night with Seth Meyers', type: 'channel', id: 'UCVTyTA7-g9nopHeHbeuvpRA', image: 'images/logos/UCVTyTA7-g9nopHeHbeuvpRA.jpg', note: 'Home of "A Closer Look".' },
            { title: 'Saturday Night Live', type: 'channel', id: 'UCqFzWxSCi39LnW1JKFR3efg', image: 'images/logos/UCqFzWxSCi39LnW1JKFR3efg.jpg', note: 'Sketches, cold opens and Weekend Update.' },
            { title: 'Taskmaster', type: 'channel', id: 'UCT5C7yaO3RVuOgwP8JVAujQ', image: 'images/logos/UCT5C7yaO3RVuOgwP8JVAujQ.jpg', note: 'Full episodes of the British comedy game show.' },
            { title: 'Key & Peele', type: 'channel', id: 'UCdN4aXTrHAtfgbVG9HjBmxQ', image: 'images/logos/UCdN4aXTrHAtfgbVG9HjBmxQ.jpg', note: 'Classic sketches.' },
            { title: 'Top Gear', type: 'channel', id: 'UCjOl2AUblVmg2rA_cRgZkFg', image: 'images/logos/UCjOl2AUblVmg2rA_cRgZkFg.jpg', note: 'Cars, challenges and road trips.' },
            { title: 'Hot Ones', type: 'channel', id: 'UCPD_bxCRGpmmeQcbe2kpPaA', image: 'images/logos/UCPD_bxCRGpmmeQcbe2kpPaA.jpg', note: 'Celebrity interviews over increasingly spicy wings.' },
            { title: 'Good Mythical Morning', type: 'channel', id: 'UC4PooiX37Pld1T8J5SYT-SQ', image: 'images/logos/UC4PooiX37Pld1T8J5SYT-SQ.jpg', note: 'Rhett and Link\'s daily show.' },
            { title: '60 Minutes', type: 'channel', id: 'UCsN32BtMd0IoByjJRNF12cw', image: 'images/logos/UCsN32BtMd0IoByjJRNF12cw.jpg', note: 'Investigations and interviews from CBS News.' }
        ]
    },
    {
        title: 'Documentaries',
        items: [
            { title: 'DW Documentary', type: 'channel', id: 'UCW39zufHfsuGgpLviKh297Q', image: 'images/logos/UCW39zufHfsuGgpLviKh297Q.jpg', note: 'Full-length documentaries from around the world.' },
            { title: 'FRONTLINE PBS', type: 'channel', id: 'UC3ScyryU9Oy9Wse3a8OAmYQ', image: 'images/logos/UC3ScyryU9Oy9Wse3a8OAmYQ.jpg', note: 'Award-winning investigative films, free in full.' },
            { title: 'BBC Earth', type: 'channel', id: 'UCwmZiChSryoWQCZMIQezgTg', image: 'images/logos/UCwmZiChSryoWQCZMIQezgTg.jpg', note: 'Nature and wildlife from the BBC.' },
            { title: 'National Geographic', type: 'channel', id: 'UCpVm7bg6pXKo1Pr6k5kxG9A', image: 'images/logos/UCpVm7bg6pXKo1Pr6k5kxG9A.jpg', note: 'Science, exploration and adventure.' },
            { title: 'Free Documentary', type: 'channel', id: 'UCijcd0GR0fkxCAZwkiuWqtQ', image: 'images/logos/UCijcd0GR0fkxCAZwkiuWqtQ.jpg', note: 'Full documentaries on nature, travel and engineering.' },
            { title: 'Real Stories', type: 'channel', id: 'UCu4XcDBdnZkV6-5z2f16M0g', image: 'images/logos/UCu4XcDBdnZkV6-5z2f16M0g.jpg', note: 'Human-interest documentaries.' },
            { title: 'Timeline', type: 'channel', id: 'UC88lvyJe7aHZmcvzvubDFRg', image: 'images/logos/UC88lvyJe7aHZmcvzvubDFRg.jpg', note: 'World history documentaries.' },
            { title: 'LEMMiNO', type: 'channel', id: 'UCRcgy6GzDeccI7dkbbBna3Q', image: 'images/logos/UCRcgy6GzDeccI7dkbbBna3Q.jpg', note: 'Meticulous films on mysteries and history.' },
            { title: 'Johnny Harris', type: 'channel', id: 'UCmGSJVG3mCRXVOP4yZrU1Dw', image: 'images/logos/UCmGSJVG3mCRXVOP4yZrU1Dw.jpg', note: 'Visual journalism on geopolitics and maps.' },
            { title: 'Vox', type: 'channel', id: 'UCLXo7UDZvByw2ixzpQCufnA', image: 'images/logos/UCLXo7UDZvByw2ixzpQCufnA.jpg', note: 'Explainers on news, culture and science.' },
            { title: 'VICE', type: 'channel', id: 'UCn8zNIfYAQNdrFRrr8oibKw', image: 'images/logos/UCn8zNIfYAQNdrFRrr8oibKw.jpg', note: 'On-the-ground reporting and culture.' },
            { title: 'Al Jazeera English', type: 'channel', id: 'UCNye-wNBqNL5ZzHSJj3l8Bg', image: 'images/logos/UCNye-wNBqNL5ZzHSJj3l8Bg.jpg', note: 'International news and documentaries.' }
        ]
    },
    {
        title: 'Science & Learning',
        items: [
            { title: 'Kurzgesagt', type: 'channel', id: 'UCsXVk37bltHxD1rDPwtNM8Q', image: 'images/logos/UCsXVk37bltHxD1rDPwtNM8Q.jpg', note: 'Beautifully animated explainers about science and life.' },
            { title: 'Veritasium', type: 'channel', id: 'UCHnyfMqiRRG1u-2MsSQLbXA', image: 'images/logos/UCHnyfMqiRRG1u-2MsSQLbXA.jpg', note: 'Science and engineering stories, deeply researched.' },
            { title: '3Blue1Brown', type: 'channel', id: 'UCYO_jab_esuFRV4b17AJtAw', image: 'images/logos/UCYO_jab_esuFRV4b17AJtAw.jpg', note: 'Maths made visual.' },
            { title: 'Mark Rober', type: 'channel', id: 'UCY1kMZp36IQSyNx_9h4mpCg', image: 'images/logos/UCY1kMZp36IQSyNx_9h4mpCg.jpg', note: 'Engineering builds and experiments.' },
            { title: 'SmarterEveryDay', type: 'channel', id: 'UC6107grRI4m0o2-emgoDnAA', image: 'images/logos/UC6107grRI4m0o2-emgoDnAA.jpg', note: 'Destin explores how things work.' },
            { title: 'Vsauce', type: 'channel', id: 'UC6nSFpj9HTCZ5t-N3Rm3-HA', image: 'images/logos/UC6nSFpj9HTCZ5t-N3Rm3-HA.jpg', note: 'Curious questions, surprising answers.' },
            { title: 'Steve Mould', type: 'channel', id: 'UCEIwxahdLz7bap-VDs9h35A', image: 'images/logos/UCEIwxahdLz7bap-VDs9h35A.jpg', note: 'Physics you can see on a desk.' },
            { title: 'Tom Scott', type: 'channel', id: 'UCBa659QWEk1AI4Tg--mrJ2A', image: 'images/logos/UCBa659QWEk1AI4Tg--mrJ2A.jpg', note: 'Amazing places and things you might not know.' },
            { title: 'Numberphile', type: 'channel', id: 'UCoxcjq-8xIDTYp3uz647V5A', image: 'images/logos/UCoxcjq-8xIDTYp3uz647V5A.jpg', note: 'Mathematicians on numbers.' },
            { title: 'PBS Space Time', type: 'channel', id: 'UC7_gcs09iThXybpVgjHZ_7g', image: 'images/logos/UC7_gcs09iThXybpVgjHZ_7g.jpg', note: 'Astrophysics, taken seriously.' },
            { title: 'OverSimplified', type: 'channel', id: 'UCNIuvl7V8zACPpTmmNIqP2A', image: 'images/logos/UCNIuvl7V8zACPpTmmNIqP2A.jpg', note: 'History, animated and funny.' },
            { title: 'CrashCourse', type: 'channel', id: 'UCX6b17PVsYBQ0ip5gyeme-Q', image: 'images/logos/UCX6b17PVsYBQ0ip5gyeme-Q.jpg', note: 'Whole courses in short episodes.' },
            { title: 'TED', type: 'channel', id: 'UCAuUUnT6oDeKwE6v1NGQxug', image: 'images/logos/UCAuUUnT6oDeKwE6v1NGQxug.jpg', note: 'Talks worth watching.' },
            { title: 'NASA', type: 'channel', id: 'UCLA_DiR1FfKNvjuUpBHmylQ', image: 'images/logos/UCLA_DiR1FfKNvjuUpBHmylQ.jpg', note: 'Launches, missions and live coverage.' },
            { title: 'Primitive Technology', type: 'channel', id: 'UCAL3JXZSzSm8AlZyD3nQdBA', image: 'images/logos/UCAL3JXZSzSm8AlZyD3nQdBA.jpg', note: 'Building from scratch in the wild, no talking.' }
        ]
    },
    {
        title: 'Tech & Engineering',
        items: [
            { title: 'Marques Brownlee', type: 'channel', id: 'UCBJycsmduvYEL83R_U4JriQ', image: 'images/logos/UCBJycsmduvYEL83R_U4JriQ.jpg', note: 'The benchmark for tech reviews.' },
            { title: 'Mrwhosetheboss', type: 'channel', id: 'UCMiJRAwDNSNzuYeN2uWa0pA', image: 'images/logos/UCMiJRAwDNSNzuYeN2uWa0pA.jpg', note: 'Phones and gadgets, tested.' },
            { title: 'Linus Tech Tips', type: 'channel', id: 'UCXuqSBlHAE6Xw-yeJA0Tunw', image: 'images/logos/UCXuqSBlHAE6Xw-yeJA0Tunw.jpg', note: 'PC hardware and builds.' },
            { title: 'The Verge', type: 'channel', id: 'UCddiUEpeqJcYeBxX1IVBKvQ', image: 'images/logos/UCddiUEpeqJcYeBxX1IVBKvQ.jpg', note: 'Tech news and reviews.' },
            { title: 'ColdFusion', type: 'channel', id: 'UC4QZ_LsYcvcq7qOsOhpAX4A', image: 'images/logos/UC4QZ_LsYcvcq7qOsOhpAX4A.jpg', note: 'Stories of technology and business.' },
            { title: 'Fireship', type: 'channel', id: 'UCsBjURrPoezykLs9EqgamOA', image: 'images/logos/UCsBjURrPoezykLs9EqgamOA.jpg', note: 'Fast, funny software news.' },
            { title: 'Two Minute Papers', type: 'channel', id: 'UCbfYPyITQ-7l4upoX8nvctg', image: 'images/logos/UCbfYPyITQ-7l4upoX8nvctg.jpg', note: 'AI research, explained briefly.' },
            { title: 'Computerphile', type: 'channel', id: 'UC9-y-6csu5WGm29I7JiwpnA', image: 'images/logos/UC9-y-6csu5WGm29I7JiwpnA.jpg', note: 'Computer science explained by academics.' },
            { title: 'Real Engineering', type: 'channel', id: 'UCR1IuLEqb6UEA_zQ81kwXfg', image: 'images/logos/UCR1IuLEqb6UEA_zQ81kwXfg.jpg', note: 'How great machines are engineered.' },
            { title: 'Practical Engineering', type: 'channel', id: 'UCMOqf8ab-42UUQIdVoKwjlQ', image: 'images/logos/UCMOqf8ab-42UUQIdVoKwjlQ.jpg', note: 'Civil engineering with models.' },
            { title: 'Wendover Productions', type: 'channel', id: 'UC9RM-iSvTu1uPJb8X5yp3EQ', image: 'images/logos/UC9RM-iSvTu1uPJb8X5yp3EQ.jpg', note: 'Logistics, economics and how the world works.' }
        ]
    },
    {
        title: 'Food & Travel',
        items: [
            { title: 'Gordon Ramsay', type: 'channel', id: 'UCIEv3lZ_tNXHzL3ox-_uUGQ', image: 'images/logos/UCIEv3lZ_tNXHzL3ox-_uUGQ.jpg', note: 'Recipes and the best of his shows.' },
            { title: 'Bon Appétit', type: 'channel', id: 'UCbpMy0Fg74eXXkvxJrtEn3w', image: 'images/logos/UCbpMy0Fg74eXXkvxJrtEn3w.jpg', note: 'Test-kitchen cooking.' },
            { title: 'Binging with Babish', type: 'channel', id: 'UCJHA_jMfCvEnv-3kRjTCQXw', image: 'images/logos/UCJHA_jMfCvEnv-3kRjTCQXw.jpg', note: 'Dishes from films and TV, recreated.' },
            { title: 'Joshua Weissman', type: 'channel', id: 'UChBEbMKI1eCcejTtmI32UEw', image: 'images/logos/UChBEbMKI1eCcejTtmI32UEw.jpg', note: 'Homemade versions of everything.' },
            { title: 'Mark Wiens', type: 'channel', id: 'UCyEd6QBSgat5kkC6svyjudA', image: 'images/logos/UCyEd6QBSgat5kkC6svyjudA.jpg', note: 'Street food around the world.' },
            { title: 'Best Ever Food Review Show', type: 'channel', id: 'UCcAd5Np7fO8SeejB1FVKcYw', image: 'images/logos/UCcAd5Np7fO8SeejB1FVKcYw.jpg', note: 'Adventurous food travel.' },
            { title: 'Rick Steves\' Europe', type: 'channel', id: 'UCchgIh8Tc4sTmBfnMQ5pDdg', image: 'images/logos/UCchgIh8Tc4sTmBfnMQ5pDdg.jpg', note: 'Full travel episodes across Europe.' },
            { title: 'Kara and Nate', type: 'channel', id: 'UC4ijq8Cg-8zQKx8OH12dUSw', image: 'images/logos/UC4ijq8Cg-8zQKx8OH12dUSw.jpg', note: 'Travel adventures.' },
            { title: 'Yes Theory', type: 'channel', id: 'UCvK4bOhULCpmLabd2pDMtnA', image: 'images/logos/UCvK4bOhULCpmLabd2pDMtnA.jpg', note: 'Seeking discomfort around the world.' }
        ]
    }
];
