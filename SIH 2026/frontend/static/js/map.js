/**
 * Leaflet Map Visualization Controller for SIH 2026 Drone Ingestion System.
 * Renders drone camera positions, flight trajectory, heading cones, and GCP targets.
 */

class DroneMapController {
  constructor(containerId) {
    this.containerId = containerId;
    this.map = null;
    this.imageMarkersLayer = L.layerGroup();
    this.trajectoryLayer = L.layerGroup();
    this.headingLayer = L.layerGroup();
    this.gcpLayer = L.layerGroup();
    this.allBounds = null;
    this.markerMap = {}; // image_id -> marker

    this.initMap();
  }

  initMap() {
    // Default center (Austria/Burgenland near Helenenschacht: 47.643, 16.476)
    this.map = L.map(this.containerId, {
      center: [47.6435, 16.476],
      zoom: 17,
      maxZoom: 22,
    });

    // Dark Matter tile layer for high-contrast GIS display
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>, OpenStreetMap contributors',
      maxZoom: 22,
    }).addTo(this.map);

    this.imageMarkersLayer.addTo(this.map);
    this.trajectoryLayer.addTo(this.map);
    this.headingLayer.addTo(this.map);
    this.gcpLayer.addTo(this.map);
  }

  loadGeoJson(geoJsonData, onSelectImage) {
    this.imageMarkersLayer.clearLayers();
    this.trajectoryLayer.clearLayers();
    this.headingLayer.clearLayers();
    this.gcpLayer.clearLayers();
    this.markerMap = {};

    if (!geoJsonData || !geoJsonData.features) return;

    // 1. Draw Trajectory LineString
    if (geoJsonData.trajectory && geoJsonData.trajectory.geometry) {
      const coords = geoJsonData.trajectory.geometry.coordinates.map(c => [c[1], c[0]]);
      const polyline = L.polyline(coords, {
        color: '#3B82F6',
        weight: 2.5,
        opacity: 0.7,
        dashArray: '4, 6',
      });
      this.trajectoryLayer.addLayer(polyline);
    }

    // 2. Draw Image Point Markers & Heading Vectors
    geoJsonData.features.forEach(feat => {
      const p = feat.properties;
      const [lon, lat] = feat.geometry.coordinates;

      // Marker color based on quality
      let markerColor = '#10B981'; // Good (Green)
      if (p.quality_status === 'WARNING') markerColor = '#F59E0B'; // Warning (Yellow)
      if (p.quality_status === 'BAD' || p.validation_status === 'INVALID') markerColor = '#EF4444'; // Bad (Red)

      const marker = L.circleMarker([lat, lon], {
        radius: 6,
        fillColor: markerColor,
        color: '#FFFFFF',
        weight: 1.5,
        opacity: 0.9,
        fillOpacity: 0.85,
      });

      // Popup card
      const popupHtml = `
        <div class="map-popup-card">
          ${p.thumbnail_url ? `<img src="${p.thumbnail_url}" class="map-popup-thumb" alt="${p.filename}">` : ''}
          <div class="map-popup-title">${p.filename}</div>
          <div class="map-popup-meta">
            Alt: ${p.altitude_ellipsoidal ? p.altitude_ellipsoidal.toFixed(1) + 'm' : 'N/A'}<br>
            RTK: ${p.rtk_status || 'UNKNOWN'}<br>
            Quality: <span style="color: ${markerColor}; font-weight: bold;">${p.quality_status}</span>
          </div>
        </div>
      `;
      marker.bindPopup(popupHtml);

      marker.on('click', () => {
        if (onSelectImage) onSelectImage(p.image_id);
      });

      this.imageMarkersLayer.addLayer(marker);
      this.markerMap[p.image_id] = marker;

      // 3. Draw Camera Heading Direction Ray / Cone
      if (p.heading !== null && p.heading !== undefined) {
        const rad = (p.heading - 90) * (Math.PI / 180);
        const rayLen = 0.00018; // ~15 meters in degrees
        const endLat = lat - (rayLen * Math.sin(rad));
        const endLon = lon + (rayLen * Math.cos(rad));

        const ray = L.polyline([[lat, lon], [endLat, endLon]], {
          color: '#60A5FA',
          weight: 1.5,
          opacity: 0.6,
        });
        this.headingLayer.addLayer(ray);
      }
    });

    // 4. Draw GCP Markers (Ground Control Points)
    if (geoJsonData.gcps && geoJsonData.gcps.length > 0) {
      geoJsonData.gcps.forEach(gcpFeat => {
        const gp = gcpFeat.properties;
        const [glon, glat] = gcpFeat.geometry.coordinates;

        // Custom diamond icon for GCP
        const gcpIcon = L.divIcon({
          className: 'gcp-marker-icon',
          html: `<div style="background: #EC4899; color: #fff; width: 14px; height: 14px; transform: rotate(45deg); border: 2px solid #fff; box-shadow: 0 0 6px rgba(236,72,153,0.8);"></div>`,
          iconSize: [14, 14],
          iconAnchor: [7, 7],
        });

        const gcpMarker = L.marker([glat, glon], { icon: gcpIcon });
        gcpMarker.bindPopup(`
          <div style="font-family: var(--font-mono); font-size: 0.75rem;">
            <b style="color: #EC4899;">GCP Target: ${gp.name}</b><br>
            Elevation: ${gp.elevation ? gp.elevation.toFixed(3) + 'm' : 'N/A'}<br>
            Ties: ${gp.associated_images_count} images
          </div>
        `);
        this.gcpLayer.addLayer(gcpMarker);
      });
    }

    // Auto-fit bounds
    if (geoJsonData.bounds) {
      const b = geoJsonData.bounds;
      this.allBounds = L.latLngBounds([b.min_lat, b.min_lon], [b.max_lat, b.max_lon]);
      this.map.fitBounds(this.allBounds, { padding: [40, 40] });
    }
  }

  selectImage(imageId) {
    const marker = this.markerMap[imageId];
    if (marker) {
      this.map.panTo(marker.getLatLng(), { animate: true });
      marker.openPopup();
    }
  }

  fitBounds() {
    if (this.allBounds) {
      this.map.fitBounds(this.allBounds, { padding: [40, 40] });
    }
  }

  toggleTrajectory(visible) {
    if (visible) this.map.addLayer(this.trajectoryLayer);
    else this.map.removeLayer(this.trajectoryLayer);
  }

  toggleGcps(visible) {
    if (visible) this.map.addLayer(this.gcpLayer);
    else this.map.removeLayer(this.gcpLayer);
  }

  toggleHeadings(visible) {
    if (visible) this.map.addLayer(this.headingLayer);
    else this.map.removeLayer(this.headingLayer);
  }
}

window.DroneMapController = DroneMapController;
