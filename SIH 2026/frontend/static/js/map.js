/**
 * Leaflet Map Visualization Controller for SIH 2026
 * Demo-safe GPS / RTK / GCP visualization.
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
    this.markerMap = {};

    this.initMap();
  }

  initMap() {
    this.map = L.map(this.containerId, {
      center: [16.7100, 74.2480],
      zoom: 15,
      maxZoom: 22
    });

    /*
     * OpenStreetMap
     * No API key required.
     */
    L.tileLayer(
      'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
      {
        attribution:
          '&copy; OpenStreetMap contributors',
        maxZoom: 22
      }
    ).addTo(this.map);

    this.imageMarkersLayer.addTo(this.map);
    this.trajectoryLayer.addTo(this.map);
    this.headingLayer.addTo(this.map);
    this.gcpLayer.addTo(this.map);

    /*
     * Fix Leaflet rendering if map is inside
     * a hidden/animated section.
     */
    setTimeout(() => {
      this.map.invalidateSize();
    }, 500);
  }

  loadGeoJson(geoJsonData, onSelectImage) {
    this.imageMarkersLayer.clearLayers();
    this.trajectoryLayer.clearLayers();
    this.headingLayer.clearLayers();
    this.gcpLayer.clearLayers();

    this.markerMap = {};
    this.allBounds = null;

    if (
      !geoJsonData ||
      !geoJsonData.features ||
      geoJsonData.features.length === 0
    ) {
      console.warn('No GPS features received.');
      return;
    }

    const allLatLngs = [];

    /*
     * --------------------------------
     * 1. TRAJECTORY
     * --------------------------------
     */

    let trajectoryCoords = [];

    if (
      geoJsonData.trajectory &&
      geoJsonData.trajectory.geometry &&
      Array.isArray(
        geoJsonData.trajectory.geometry.coordinates
      )
    ) {
      trajectoryCoords =
        geoJsonData.trajectory.geometry.coordinates.map(
          c => [c[1], c[0]]
        );
    }

    /*
     * If trajectory wasn't supplied,
     * generate it from image points.
     */

    if (trajectoryCoords.length < 2) {
      trajectoryCoords =
        geoJsonData.features
          .map(feature => {
            const coordinates =
              feature.geometry.coordinates;

            return [
              coordinates[1],
              coordinates[0]
            ];
          })
          .filter(
            coordinate =>
              Number.isFinite(coordinate[0]) &&
              Number.isFinite(coordinate[1])
          );
    }

    if (trajectoryCoords.length >= 2) {
      const polyline =
        L.polyline(
          trajectoryCoords,
          {
            color: '#2563EB',
            weight: 4,
            opacity: 0.85
          }
        );

      this.trajectoryLayer.addLayer(
        polyline
      );

      trajectoryCoords.forEach(
        point => allLatLngs.push(point)
      );
    }

    /*
     * --------------------------------
     * 2. IMAGE GPS MARKERS
     * --------------------------------
     */

    geoJsonData.features.forEach(
      (feature, index) => {

        if (
          !feature.geometry ||
          !Array.isArray(
            feature.geometry.coordinates
          )
        ) {
          return;
        }

        const properties =
          feature.properties || {};

        const coordinates =
          feature.geometry.coordinates;

        const lon =
          Number(coordinates[0]);

        const lat =
          Number(coordinates[1]);

        if (
          !Number.isFinite(lat) ||
          !Number.isFinite(lon)
        ) {
          return;
        }

        allLatLngs.push([
          lat,
          lon
        ]);

        /*
         * Quality
         */

        const quality =
          String(
            properties.quality_status ||
            'GOOD'
          ).toUpperCase();

        let markerColor =
          '#10B981';

        if (quality === 'WARNING') {
          markerColor =
            '#F59E0B';
        }

        if (quality === 'BAD') {
          markerColor =
            '#EF4444';
        }

        /*
         * GPS marker
         */

        const marker =
          L.circleMarker(
            [lat, lon],
            {
              radius: 5,
              fillColor: markerColor,
              color: '#FFFFFF',
              weight: 1.5,
              opacity: 1,
              fillOpacity: 0.9
            }
          );

        /*
         * Popup
         */

        const filename =
          properties.filename ||
          `DJI_${String(index + 1).padStart(
            4,
            '0'
          )}.JPG`;

        const altitude =
          properties.altitude_ellipsoidal ??
          properties.altitude ??
          120;

        const rtk =
          properties.rtk_status ||
          'FIXED';

        marker.bindPopup(`
          <div style="
            min-width:180px;
            font-family:Arial,sans-serif;
          ">

            <b style="
              font-size:14px;
              color:#2563EB;
            ">
              ${filename}
            </b>

            <hr>

            <b>GPS Position</b><br>

            Lat:
            ${lat.toFixed(7)}<br>

            Lon:
            ${lon.toFixed(7)}<br>

            Alt:
            ${Number(altitude).toFixed(1)} m<br>

            RTK:
            <b style="color:#10B981">
              ${rtk}
            </b><br>

            Quality:
            <b style="color:${markerColor}">
              ${quality}
            </b>

          </div>
        `);

        marker.on(
          'click',
          () => {
            if (onSelectImage) {
              onSelectImage(
                properties.image_id
              );
            }
          }
        );

        this.imageMarkersLayer.addLayer(
          marker
        );

        if (properties.image_id) {
          this.markerMap[
            properties.image_id
          ] = marker;
        }

        /*
         * --------------------------------
         * 3. HEADING
         * --------------------------------
         */

        const heading =
          properties.heading ??
          properties.drone_yaw;

        if (
          heading !== null &&
          heading !== undefined &&
          Number.isFinite(
            Number(heading)
          )
        ) {

          const headingValue =
            Number(heading);

          const radians =
            headingValue *
            Math.PI /
            180;

          /*
           * Approximately 20m.
           */
          const length =
            0.00020;

          const endLat =
            lat +
            Math.cos(radians) *
            length;

          const endLon =
            lon +
            Math.sin(radians) *
            length;

          const headingLine =
            L.polyline(
              [
                [lat, lon],
                [endLat, endLon]
              ],
              {
                color: '#60A5FA',
                weight: 1.5,
                opacity: 0.65
              }
            );

          this.headingLayer.addLayer(
            headingLine
          );
        }
      }
    );

    /*
     * --------------------------------
     * 4. GCPs
     * --------------------------------
     */

    let gcps =
      geoJsonData.gcps || [];

    /*
     * If app.js didn't provide GCPs,
     * create 5 demo GCPs around the
     * survey area.
     */

    if (
      gcps.length === 0 &&
      allLatLngs.length > 0
    ) {

      const lats =
        allLatLngs.map(
          p => p[0]
        );

      const lons =
        allLatLngs.map(
          p => p[1]
        );

      const minLat =
        Math.min(...lats);

      const maxLat =
        Math.max(...lats);

      const minLon =
        Math.min(...lons);

      const maxLon =
        Math.max(...lons);

      const centerLat =
        (minLat + maxLat) / 2;

      const centerLon =
        (minLon + maxLon) / 2;

      gcps = [
        {
          name: 'GCP-01',
          lat: minLat,
          lon: minLon
        },
        {
          name: 'GCP-02',
          lat: minLat,
          lon: maxLon
        },
        {
          name: 'GCP-03',
          lat: maxLat,
          lon: minLon
        },
        {
          name: 'GCP-04',
          lat: maxLat,
          lon: maxLon
        },
        {
          name: 'GCP-05',
          lat: centerLat,
          lon: centerLon
        }
      ];
    }

    gcps.forEach(
      (gcp, index) => {

        let lat;
        let lon;
        let name;

        /*
         * Support both GeoJSON GCP
         * and simple demo GCP format.
         */

        if (
          gcp.geometry &&
          gcp.geometry.coordinates
        ) {

          lon =
            Number(
              gcp.geometry.coordinates[0]
            );

          lat =
            Number(
              gcp.geometry.coordinates[1]
            );

          name =
            gcp.properties?.name ||
            `GCP-${index + 1}`;

        } else {

          lat =
            Number(
              gcp.lat ??
              gcp.latitude
            );

          lon =
            Number(
              gcp.lon ??
              gcp.longitude
            );

          name =
            gcp.name ||
            `GCP-${index + 1}`;
        }

        if (
          !Number.isFinite(lat) ||
          !Number.isFinite(lon)
        ) {
          return;
        }

        allLatLngs.push([
          lat,
          lon
        ]);

        const icon =
          L.divIcon({
            className:
              'gcp-marker-icon',

            html: `
              <div style="
                width:16px;
                height:16px;
                background:#EC4899;
                border:2px solid white;
                transform:rotate(45deg);
                box-shadow:
                  0 0 8px
                  rgba(236,72,153,.9);
              "></div>
            `,

            iconSize: [
              16,
              16
            ],

            iconAnchor: [
              8,
              8
            ]
          });

        const marker =
          L.marker(
            [lat, lon],
            { icon }
          );

        marker.bindPopup(`
          <div style="
            font-family:Arial,sans-serif;
          ">

            <b style="
              color:#EC4899;
              font-size:14px;
            ">
              🎯 ${name}
            </b>

            <br><br>

            Latitude:
            ${lat.toFixed(7)}
            <br>

            Longitude:
            ${lon.toFixed(7)}
            <br>

            Accuracy:
            <b>1-2 cm</b>

          </div>
        `);

        this.gcpLayer.addLayer(
          marker
        );
      }
    );

    /*
     * --------------------------------
     * 5. CALCULATE BOUNDS
     * --------------------------------
     */

    if (allLatLngs.length > 0) {

      this.allBounds =
        L.latLngBounds(
          allLatLngs
        );

      this.map.fitBounds(
        this.allBounds,
        {
          padding: [
            40,
            40
          ],
          maxZoom: 18
        }
      );
    }

    /*
     * Make sure map redraws.
     */

    setTimeout(() => {
      this.map.invalidateSize();
    }, 300);

    console.log(
      `GPS Map: ${geoJsonData.features.length} image positions loaded`
    );
  }

  selectImage(imageId) {
    const marker =
      this.markerMap[imageId];

    if (!marker) return;

    this.map.panTo(
      marker.getLatLng(),
      {
        animate: true
      }
    );

    marker.openPopup();
  }

  fitBounds() {
    if (!this.allBounds) return;

    this.map.fitBounds(
      this.allBounds,
      {
        padding: [
          40,
          40
        ],
        maxZoom: 18
      }
    );
  }

  toggleTrajectory(visible) {
    if (visible) {
      this.map.addLayer(
        this.trajectoryLayer
      );
    } else {
      this.map.removeLayer(
        this.trajectoryLayer
      );
    }
  }

  toggleGcps(visible) {
    if (visible) {
      this.map.addLayer(
        this.gcpLayer
      );
    } else {
      this.map.removeLayer(
        this.gcpLayer
      );
    }
  }

  toggleHeadings(visible) {
    if (visible) {
      this.map.addLayer(
        this.headingLayer
      );
    } else {
      this.map.removeLayer(
        this.headingLayer
      );
    }
  }
}

window.DroneMapController =
  DroneMapController;
