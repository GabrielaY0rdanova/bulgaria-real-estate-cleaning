-- =============================================================================
-- real_estate_cleaning — PostgreSQL DDL
-- Source: imot.bg scraper output
-- Purpose: Normalized schema for real estate listings and properties
-- Usage:   Safe to re-run — drops all objects and recreates from scratch.
-- =============================================================================

-- =============================================================================
-- DROP EXISTING OBJECTS (reverse dependency order)
-- =============================================================================
-- Tables dropped first (child → parent), then enum types.
-- CASCADE ensures dependent objects (constraints, indices) are removed.
-- IF EXISTS prevents errors on first run against an empty database.
-- =============================================================================

DROP TABLE IF EXISTS pipeline_runs CASCADE;
DROP TABLE IF EXISTS price_history CASCADE;
DROP TABLE IF EXISTS property_features CASCADE;
DROP TABLE IF EXISTS listings CASCADE;
DROP TABLE IF EXISTS properties CASCADE;
DROP TABLE IF EXISTS contacts CASCADE;
DROP TABLE IF EXISTS features CASCADE;
DROP TABLE IF EXISTS property_types CASCADE;
DROP TABLE IF EXISTS construction_types CASCADE;
DROP TABLE IF EXISTS geographies CASCADE;

DROP TYPE IF EXISTS listing_status CASCADE;
DROP TYPE IF EXISTS tec_type CASCADE;
DROP TYPE IF EXISTS construction_status CASCADE;
DROP TYPE IF EXISTS transaction_type CASCADE;
DROP TYPE IF EXISTS contact_type CASCADE;

-- =============================================================================
-- ENUM TYPES
-- =============================================================================
-- Defined first because they are referenced by multiple tables below.
-- This avoids forward-reference issues and improves schema readability when
-- viewing the file top-to-bottom.
-- =============================================================================

CREATE TYPE contact_type AS ENUM ('agency', 'owner');
CREATE TYPE transaction_type AS ENUM ('sale', 'rental');
CREATE TYPE construction_status AS ENUM ('completed', 'under_construction', 'not_completed');
CREATE TYPE tec_type AS ENUM ('district_heating', 'no_district_heating', 'local_heating', 'being_installed');
CREATE TYPE listing_status AS ENUM ('active', 'inactive');

-- =============================================================================
-- geographies
-- Purpose: Hierarchical geographic structure (country → area)
-- Notes:
--   - Self-referencing via parent_id
--   - Top-level rows have parent_id = NULL
--   - locality_type applies only when level = 'locality'
-- =============================================================================

CREATE TABLE geographies (
    geo_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_id INT NULL,
    level VARCHAR(20) NOT NULL CHECK (level IN ('region', 'locality', 'area')),
    name_bg VARCHAR(255) NOT NULL,
    name_en VARCHAR(255) NOT NULL,
    locality_type VARCHAR(50) NULL,

    CONSTRAINT fk_parent_geography
        FOREIGN KEY (parent_id)
        REFERENCES geographies(geo_id)
        ON DELETE RESTRICT
);

-- =============================================================================
-- construction_types
-- Purpose: Lookup table for construction types (BG/EN)
-- =============================================================================

CREATE TABLE construction_types (
    construction_type_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name_bg VARCHAR (255) NOT NULL,
    name_en VARCHAR (255) NOT NULL,

    CONSTRAINT uq_construction_types_name_bg UNIQUE (name_bg)
);

-- =============================================================================
-- property_types
-- Purpose: Lookup table for property classification
-- Notes:
--   - category can group types (e.g. residential, commercial)
-- =============================================================================

CREATE TABLE property_types (
    property_type_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name_bg VARCHAR (255) NOT NULL,
    name_en VARCHAR (255) NOT NULL,
    category VARCHAR (255),

    CONSTRAINT uq_property_types_name_bg UNIQUE (name_bg)
);

-- =============================================================================
-- features
-- Purpose: Lookup table for property features/amenities
-- =============================================================================

CREATE TABLE features (
    feature_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name_bg VARCHAR (255) NOT NULL,
    name_en VARCHAR (255) NOT NULL,

    CONSTRAINT uq_features_name_bg UNIQUE (name_bg)
);

-- =============================================================================
-- contacts
-- Purpose: Listing contact entity (agency or owner)
-- =============================================================================

CREATE TABLE contacts (
    contact_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contact_type contact_type,
    name VARCHAR (255),
    phone VARCHAR (50)
);

-- =============================================================================
-- properties
-- Purpose: Core entity describing the physical real estate asset
-- Notes:
--   - One-to-one relationship with listings (each listing has its own property record)
--   - No shared property identity across multiple listings (no deduplication at property level)
--   - Some attributes may be NULL due to incomplete scraped data
-- =============================================================================

CREATE TABLE properties (
    property_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    geo_id INT NOT NULL,
    property_type_id INT NOT NULL,
    construction_type_id INT,
    bedrooms INT,
    area_m2 NUMERIC(12,2),
    floor INT,
    total_floors INT,
    construction_status construction_status,
    year_built INT,
    gas BOOLEAN,
    tec tec_type,

    CONSTRAINT fk_properties_geographies
        FOREIGN KEY (geo_id)
        REFERENCES geographies(geo_id),

    CONSTRAINT fk_properties_property_types
        FOREIGN KEY (property_type_id)
        REFERENCES property_types(property_type_id),

    CONSTRAINT fk_properties_construction_types
        FOREIGN KEY (construction_type_id)
        REFERENCES construction_types(construction_type_id)
);

-- =============================================================================
-- listings
-- Purpose: Represents a scraped advertisement for a property
-- Notes:
--   - source_id is the upsert key (stable identity across scraper runs)
--   - Enables deduplication and drives listing lifecycle state changes
--     (active ↔ inactive based on presence/absence in latest scrape)
-- =============================================================================

CREATE TABLE listings (
    listing_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id VARCHAR (255) NOT NULL,
    property_id INT NOT NULL,
    contact_id INT NOT NULL,
    transaction_type transaction_type,
    listing_tier TEXT,
    listing_url TEXT NOT NULL,
    price NUMERIC(12,2),
    price_on_request BOOLEAN NOT NULL DEFAULT FALSE,
    date_posted TIMESTAMP,
    date_modified TIMESTAMP,
    has_photos BOOLEAN,
    status listing_status,
    status_changed_at TIMESTAMP, 
    scraped_at TIMESTAMP NOT NULL,
    date_last_checked TIMESTAMP NOT NULL,

    CONSTRAINT uq_listings_source_id UNIQUE (source_id),

    CONSTRAINT fk_listings_properties
        FOREIGN KEY (property_id)
        REFERENCES properties(property_id),

    CONSTRAINT fk_listings_contacts
        FOREIGN KEY (contact_id)
        REFERENCES contacts(contact_id)
);

-- =============================================================================
-- property_features
-- Purpose: Many-to-many relationship between properties and features
-- =============================================================================

CREATE TABLE property_features (
    property_id INT,
    feature_id INT,

    CONSTRAINT fk_property_features_properties
        FOREIGN KEY (property_id) 
        REFERENCES properties(property_id),

    CONSTRAINT fk_property_features_features
        FOREIGN KEY (feature_id) 
        REFERENCES features(feature_id),

    CONSTRAINT pk_property_features PRIMARY KEY (property_id, feature_id)
);

-- =============================================================================
-- price_history
-- Purpose: Tracks price changes detected between scraper runs
-- =============================================================================

CREATE TABLE price_history (
    history_id   INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    listing_id   INT NOT NULL,
    old_price    NUMERIC(12,2),
    new_price    NUMERIC(12,2),
    changed_at   TIMESTAMP NOT NULL,

    CONSTRAINT fk_price_history_listings
        FOREIGN KEY (listing_id)
        REFERENCES listings(listing_id)
);
