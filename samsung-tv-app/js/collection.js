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
 */
var COLLECTION = [
    {
        title: 'Podcasts',
        items: [
            { title: 'Lex Fridman Podcast', type: 'channel', id: 'UCSHZKyawb77ixDdsGog4iWA', note: 'Long conversations about science, technology and history.' },
            { title: 'The Diary Of A CEO', type: 'channel', id: 'UCGq-a57w-aPwyi3pW7XLiHw', note: 'Steven Bartlett interviews founders, doctors and experts.' },
            { title: 'Huberman Lab', type: 'channel', id: 'UC2D2CMWXMOVWx7giW1n3LIg', note: 'Neuroscience and health, explained.' },
            { title: 'The Joe Rogan Experience', type: 'channel', id: 'UCzQUP1qoWDoEbmsQxvdjxgQ', note: 'Long-form interviews.' }
        ]
    },
    {
        title: 'TV Shows',
        items: [
            { title: 'Last Week Tonight', type: 'channel', id: 'UC3XTzVzaHQEd30rQbuvCtTQ', note: 'John Oliver on the week in news.' },
            { title: 'The Tonight Show', type: 'channel', id: 'UC8-Th83bH_thdKZDJCrn88g', note: 'Starring Jimmy Fallon.' },
            { title: 'The Late Show', type: 'channel', id: 'UCMtFAi84ehTSYSE9XoHefig', note: 'With Stephen Colbert.' },
            { title: 'Saturday Night Live', type: 'channel', id: 'UCqFzWxSCi39LnW1JKFR3efg', note: 'Sketches and Weekend Update.' }
        ]
    },
    {
        title: 'YouTube Channels',
        items: [
            { title: 'Kurzgesagt', type: 'channel', id: 'UCsXVk37bltHxD1rDPwtNM8Q', note: 'Animated explainers about science and life.' },
            { title: 'Veritasium', type: 'channel', id: 'UCHnyfMqiRRG1u-2MsSQLbXA', note: 'Science and engineering videos.' },
            { title: 'Marques Brownlee', type: 'channel', id: 'UCBJycsmduvYEL83R_U4JriQ', note: 'Tech reviews.' },
            { title: 'Mark Rober', type: 'channel', id: 'UCY1kMZp36IQSyNx_9h4mpCg', note: 'Engineering builds and experiments.' },
            { title: 'TED', type: 'channel', id: 'UCAuUUnT6oDeKwE6v1NGQxug', note: 'Talks worth watching.' },
            { title: 'NASA', type: 'channel', id: 'UCLA_DiR1FfKNvjuUpBHmylQ', note: 'Launches, missions and live coverage.' }
        ]
    }
];
