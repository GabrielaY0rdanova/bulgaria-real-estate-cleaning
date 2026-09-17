-- Read-only verification for a completed full rebuild.

SELECT current_database() AS database_name;

SELECT transaction_type, status, COUNT(*) AS listing_count
FROM listings
GROUP BY transaction_type, status
ORDER BY transaction_type, status;

SELECT
    COUNT(*) AS listing_count,
    COUNT(DISTINCT source_id) AS unique_source_ids,
    COUNT(*) - COUNT(DISTINCT source_id) AS duplicate_source_ids,
    COUNT(*) FILTER (WHERE date_last_checked < scraped_at) AS invalid_last_checked,
    COUNT(*) FILTER (WHERE status IS NULL) AS null_statuses
FROM listings;

SELECT
    (SELECT COUNT(*)
       FROM listings l
       LEFT JOIN properties p ON p.property_id = l.property_id
      WHERE p.property_id IS NULL) AS orphan_listing_properties,
    (SELECT COUNT(*)
       FROM listings l
       LEFT JOIN contacts c ON c.contact_id = l.contact_id
      WHERE c.contact_id IS NULL) AS orphan_listing_contacts,
    (SELECT COUNT(*)
       FROM properties p
       LEFT JOIN geographies g ON g.geo_id = p.geo_id
      WHERE g.geo_id IS NULL) AS orphan_property_geographies,
    (SELECT COUNT(*)
       FROM property_features pf
       LEFT JOIN properties p ON p.property_id = pf.property_id
      WHERE p.property_id IS NULL) AS orphan_feature_properties,
    (SELECT COUNT(*)
       FROM property_features pf
       LEFT JOIN features f ON f.feature_id = pf.feature_id
      WHERE f.feature_id IS NULL) AS orphan_feature_definitions,
    (SELECT COUNT(*)
       FROM price_history ph
       LEFT JOIN listings l ON l.listing_id = ph.listing_id
      WHERE l.listing_id IS NULL) AS orphan_price_history;

SELECT
    COUNT(*) AS price_change_count,
    COUNT(DISTINCT listing_id) AS listings_with_price_changes,
    MIN(changed_at) AS first_price_change,
    MAX(changed_at) AS last_price_change,
    COUNT(*) FILTER (WHERE old_price IS NOT DISTINCT FROM new_price)
        AS unchanged_price_history_rows
FROM price_history;
