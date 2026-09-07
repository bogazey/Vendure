interface PhotoGridItem {
    id: string;
    photoUrl: string;
    caption?: string;
    subtitle: string;
    timestamp: string;
}

function formatTimestamp(iso: string): string {
    const date = new Date(iso);
    return date.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
    });
}

export function PhotoGrid({ items }: { items: PhotoGridItem[] }) {
    return (
        <div className="photo-grid">
            {items.map(item => (
                <figure className="photo-card" key={item.id}>
                    <img src={item.photoUrl} alt={item.caption ?? item.subtitle} loading="lazy" />
                    <figcaption>
                        <div className="photo-card-subtitle">{item.subtitle}</div>
                        {item.caption && <div className="photo-card-caption">{item.caption}</div>}
                        <div className="photo-card-timestamp">{formatTimestamp(item.timestamp)}</div>
                    </figcaption>
                </figure>
            ))}
        </div>
    );
}
