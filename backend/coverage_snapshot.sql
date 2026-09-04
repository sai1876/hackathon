-- Read-only presentation snapshot. Export the returned FeatureCollection to
-- web/public/data/road-coverage.geojson after each road import.
-- Occupied ~265 x 278 m cells, NOT an administrative boundary or service guarantee.
WITH extent AS (
  SELECT ST_SetSRID(ST_Extent(geometry::geometry)::geometry, 4326) geom,
         count(*) road_count FROM public.road_segments
), occupied AS (
  SELECT cell.geom FROM extent e
  CROSS JOIN LATERAL ST_SquareGrid(0.0025, e.geom) cell
  WHERE EXISTS (
    SELECT 1 FROM public.road_segments r
    WHERE r.geometry::geometry && cell.geom
      AND ST_Intersects(r.geometry::geometry, cell.geom)
  )
), footprint AS (
  SELECT ST_Multi(ST_SimplifyPreserveTopology(ST_UnaryUnion(ST_Collect(geom)), 0.00001)) geom
  FROM occupied
)
SELECT jsonb_build_object(
  'type', 'FeatureCollection',
  'metadata', jsonb_build_object(
    'roadCount', e.road_count, 'generatedAt', now(),
    'method', 'Occupied 0.0025-degree grid cells intersecting imported road geometry',
    'approximate', true, 'source', 'OpenStreetMap / AegisGrid road_segments',
    'license', 'ODbL-1.0',
    'bounds', jsonb_build_array(ST_XMin(f.geom), ST_YMin(f.geom), ST_XMax(f.geom), ST_YMax(f.geom))),
  'features', jsonb_build_array(jsonb_build_object('type', 'Feature',
    'properties', jsonb_build_object('meaning', 'Approximate road-data presence, not guaranteed routability'),
    'geometry', ST_AsGeoJSON(f.geom, 6)::jsonb))) AS coverage
FROM extent e CROSS JOIN footprint f;
