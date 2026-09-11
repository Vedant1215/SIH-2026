/**
 * SIH 2026 - Main Application
 * Demo Mode for Vercel Prototype
 */

document.addEventListener('DOMContentLoaded', async () => {
  lucide.createIcons();

  const DEMO_MODE = true;

  let mapController = null;
  let galleryController = null;
  let viewer3dController = null;
  let reconstructController = null;

  // -----------------------------
  // Controllers
  // -----------------------------
  try {
    mapController = new DroneMapController('leaflet-map');

    galleryController = new GalleryController(
      'gallery-container',
      (selectedImageId) => {
        if (mapController) {
          mapController.selectImage(selectedImageId);
        }
      }
    );

    /*
     * IMPORTANT:
     * 3D viewer MUST load even in DEMO_MODE.
     */
    viewer3dController = new Viewer3DController(
      'viewer-canvas',
      'viewer-modal'
    );

    /*
     * Real reconstruction controller only in real mode.
     * This prevents Open3D/COLMAP/backend calls on Vercel.
     */
    if (!DEMO_MODE && typeof ReconstructionController !== 'undefined') {
      reconstructController =
        new ReconstructionController(viewer3dController);
    }

  } catch (e) {
    console.error(
      'Controller initialization error:',
      e
    );
  }

  // -----------------------------
  // Viewer Modal
  // -----------------------------
  const btnCloseViewer =
    document.getElementById('btn-close-viewer');

  const viewerModal =
    document.getElementById('viewer-modal');

  if (btnCloseViewer && viewerModal) {
    btnCloseViewer.addEventListener('click', () => {
      viewerModal.style.display = 'none';
    });

    viewerModal.addEventListener('click', (e) => {
      if (e.target === viewerModal) {
        viewerModal.style.display = 'none';
      }
    });
  }

  // -----------------------------
  // Construct 3D Button
  // -----------------------------
  /*
   * Automatically find the button whose text contains
   * "Construct 3D".
   */
  const allButtons =
    document.querySelectorAll('button');

  allButtons.forEach((button) => {
    const buttonText =
      button.textContent
        .trim()
        .toLowerCase();

    if (
      buttonText.includes('construct') &&
      buttonText.includes('3d')
    ) {
      button.addEventListener('click', () => {

        console.log(
          'Construct 3D clicked'
        );

        if (!viewer3dController) {
          console.error(
            '3D viewer controller not available.'
          );
          return;
        }

        if (viewerModal) {
          viewerModal.style.display = 'flex';
        }

        /*
         * Demo model generated completely
         * inside the browser.
         */
        viewer3dController.loadDemoModel();
      });
    }
  });

  // -----------------------------
  // Viewer Controls
  // -----------------------------
  const btnModeTextured =
    document.getElementById(
      'btn-mode-textured'
    );

  const btnModeWireframe =
    document.getElementById(
      'btn-mode-wireframe'
    );

  const btnModePoints =
    document.getElementById(
      'btn-mode-points'
    );

  const btnToggleGrid =
    document.getElementById(
      'btn-toggle-grid'
    );

  const btnToggleBBox =
    document.getElementById(
      'btn-toggle-bbox'
    );

  const btnResetCam =
    document.getElementById(
      'btn-reset-cam'
    );

  let gridVisible = true;
  let bboxVisible = true;

  if (viewer3dController) {

    // Textured
    if (btnModeTextured) {
      btnModeTextured.addEventListener(
        'click',
        () => {

          btnModeTextured.classList.add(
            'active'
          );

          if (btnModeWireframe) {
            btnModeWireframe.classList.remove(
              'active'
            );
          }

          if (btnModePoints) {
            btnModePoints.classList.remove(
              'active'
            );
          }

          viewer3dController.setMode(
            'textured'
          );
        }
      );
    }

    // Wireframe
    if (btnModeWireframe) {
      btnModeWireframe.addEventListener(
        'click',
        () => {

          btnModeWireframe.classList.add(
            'active'
          );

          if (btnModeTextured) {
            btnModeTextured.classList.remove(
              'active'
            );
          }

          if (btnModePoints) {
            btnModePoints.classList.remove(
              'active'
            );
          }

          viewer3dController.setMode(
            'wireframe'
          );
        }
      );
    }

    // Point Cloud
    if (btnModePoints) {
      btnModePoints.addEventListener(
        'click',
        () => {

          btnModePoints.classList.add(
            'active'
          );

          if (btnModeTextured) {
            btnModeTextured.classList.remove(
              'active'
            );
          }

          if (btnModeWireframe) {
            btnModeWireframe.classList.remove(
              'active'
            );
          }

          /*
           * Demo-safe point mode.
           */
          viewer3dController.setMode(
            'points'
          );
        }
      );
    }

    // Grid
    if (btnToggleGrid) {
      btnToggleGrid.addEventListener(
        'click',
        () => {

          gridVisible =
            !gridVisible;

          btnToggleGrid.classList.toggle(
            'active',
            gridVisible
          );

          viewer3dController.toggleGrid(
            gridVisible
          );
        }
      );
    }

    // Bounding Box
    if (btnToggleBBox) {
      btnToggleBBox.addEventListener(
        'click',
        () => {

          bboxVisible =
            !bboxVisible;

          btnToggleBBox.classList.toggle(
            'active',
            bboxVisible
          );

          viewer3dController.toggleBBox(
            bboxVisible
          );
        }
      );
    }

    // Reset Camera
    if (btnResetCam) {
      btnResetCam.addEventListener(
        'click',
        () => {
          viewer3dController.resetCamera();
        }
      );
    }
  }

  // -----------------------------
  // UI Elements
  // -----------------------------
  const valTotalImages =
    document.getElementById(
      'val-total-images'
    );

  const valGpsCoverage =
    document.getElementById(
      'val-gps-coverage'
    );

  const valRtkStatus =
    document.getElementById(
      'val-rtk-status'
    );

  const valGcpCount =
    document.getElementById(
      'val-gcp-count'
    );

  const datasetTag =
    document.getElementById(
      'dataset-location-tag'
    );

  const filterSearch =
    document.getElementById(
      'filter-search'
    );

  const filterGps =
    document.getElementById(
      'filter-gps'
    );

  const filterRtk =
    document.getElementById(
      'filter-rtk'
    );

  const filterQuality =
    document.getElementById(
      'filter-quality'
    );

  const filterSort =
    document.getElementById(
      'filter-sort'
    );

  const btnViewGrid =
    document.getElementById(
      'btn-view-grid'
    );

  const btnViewTable =
    document.getElementById(
      'btn-view-table'
    );

  const btnRefresh =
    document.getElementById(
      'btn-refresh'
    );

  const btnFitBounds =
    document.getElementById(
      'btn-fit-bounds'
    );

  const toggleTrajectory =
    document.getElementById(
      'toggle-trajectory'
    );

  const toggleGcps =
    document.getElementById(
      'toggle-gcps'
    );

  const toggleHeading =
    document.getElementById(
      'toggle-heading'
    );

  // -----------------------------
  // Demo Records
  // -----------------------------
  function generateDemoRecords() {
    const records = [];

    for (let i = 1; i <= 500; i++) {

      const qualityStatus =
        i % 17 === 0
          ? 'WARNING'
          : 'GOOD';

      records.push({

        image_id:
          `IMG_${String(i).padStart(4, '0')}`,

        filename:
          `DJI_${String(i).padStart(4, '0')}.JPG`,

        gps_available: true,

        gps: true,

        rtk_available: true,

        rtk: true,

        rtk_status: 'FIXED',

        quality:
          qualityStatus,

        quality_status:
          qualityStatus,

        latitude:
          16.7050 +
          (i * 0.00002),

        longitude:
          74.2433 +
          (i * 0.00002),

        altitude:
          120 +
          (i % 20),

        altitude_ellipsoidal:
          120 +
          (i % 20),

        altitude_relative:
          95 +
          (i % 15),

        heading:
          i % 360,

        drone_yaw:
          i % 360,

        camera_yaw:
          i % 360,

        camera_pitch:
          -89,

        drone_pitch:
          0,

        drone_roll:
          0,

        gps_accuracy_h:
          0.015,

        gps_accuracy_v:
          0.025,

        metadata_completeness:
          0.98,

        focal_length_mm:
          8.4,

        focal_length_35mm:
          24,

        exposure_time_s:
          0.001,

        aperture_fnumber:
          2.8,

        iso:
          100,

        camera_make:
          'Autel',

        camera_model:
          'XT705',

        timestamp:
          `2026-09-11T10:${String(
            i % 60
          ).padStart(2, '0')}:00Z`,

        rtk_flag:
          1,

        associated_gcps:
          i <= 5 ? [i] : [],

        metadata_sources:
          [
            'EXIF',
            'RTK'
          ],

        match_method:
          'Direct',

        match_confidence:
          0.99,

        gcp:
          i <= 5
      });
    }

    return records;
  }

  // -----------------------------
  // Hide Loading
  // -----------------------------
  function hideLoadingState() {

    document
      .querySelectorAll('*')
      .forEach((el) => {

        if (
          el.children.length === 0 &&
          el.textContent &&
          el.textContent
            .trim()
            .toLowerCase()
            .includes(
              'ingesting and analyzing dataset'
            )
        ) {

          const parent =
            el.closest(
              '.loading-overlay, .loading, .loader, .overlay, .modal, .status'
            );

          if (parent) {
            parent.style.display =
              'none';
          } else {
            el.style.display =
              'none';
          }
        }
      });
  }

  // -----------------------------
  // Demo Data
  // -----------------------------
  function loadDemoData() {

    const records =
      generateDemoRecords();

    if (valTotalImages) {
      valTotalImages.textContent =
        '500';
    }

    if (valGpsCoverage) {
      valGpsCoverage.textContent =
        '500 / 500';
    }

    if (valRtkStatus) {
      valRtkStatus.textContent =
        'Fixed (1-2cm)';
    }

    if (valGcpCount) {
      valGcpCount.textContent =
        '5 Verified';
    }

    if (datasetTag) {
      datasetTag.textContent =
        'Dataset: SIH 2026 Demo Dataset';
    }

    if (galleryController) {
      galleryController.setRecords(
        records
      );
    }

    // -----------------------------
    // Demo Map
    // -----------------------------
    if (mapController) {

      const features =
        records.map(
          (record) => ({

            type: 'Feature',

            properties: {

              image_id:
                record.image_id,

              filename:
                record.filename,

              quality_status:
                record.quality_status,

              rtk_status:
                record.rtk_status,

              altitude_ellipsoidal:
                record.altitude_ellipsoidal,

              heading:
                record.heading
            },

            geometry: {

              type: 'Point',

              coordinates: [
                record.longitude,
                record.latitude
              ]
            }
          })
        );

      // -----------------------------
      // Bounds
      // -----------------------------
      const lats =
        records.map(
          r => r.latitude
        );

      const lons =
        records.map(
          r => r.longitude
        );

      const bounds = {

        min_lat:
          Math.min(...lats) -
          0.001,

        max_lat:
          Math.max(...lats) +
          0.001,

        min_lon:
          Math.min(...lons) -
          0.001,

        max_lon:
          Math.max(...lons) +
          0.001
      };

      // -----------------------------
      // Flight Trajectory
      // -----------------------------
      const trajectoryCoordinates =
        records
          .filter(
            (_, index) =>
              index % 5 === 0
          )
          .map(
            r => [
              r.longitude,
              r.latitude
            ]
          );

      const trajectory = {

        type: 'Feature',

        properties: {},

        geometry: {

          type: 'LineString',

          coordinates:
            trajectoryCoordinates
        }
      };

      // -----------------------------
      // GCPs
      // -----------------------------
      const gcps =
        records
          .slice(0, 5)
          .map(
            (record, index) => ({

              type: 'Feature',

              properties: {

                name:
                  `GCP-${index + 1}`,

                elevation:
                  record.altitude_ellipsoidal,

                associated_images_count:
                  100
              },

              geometry: {

                type: 'Point',

                coordinates: [
                  record.longitude,
                  record.latitude
                ]
              }
            })
          );

      const geoJson = {

        type:
          'FeatureCollection',

        features:
          features,

        bounds:
          bounds,

        trajectory:
          trajectory,

        gcps:
          gcps
      };

      try {

        mapController.loadGeoJson(
          geoJson,
          (clickedId) => {

            if (galleryController) {

              galleryController.selectImage(
                clickedId
              );

            }
          }
        );

      } catch (e) {

        console.error(
          'Demo map error:',
          e
        );
      }
    }

    hideLoadingState();

    console.log(
      'SIH 2026 Demo Mode: 500 records loaded'
    );
  }

  // -----------------------------
  // Load Data
  // -----------------------------
  async function loadData() {

    if (DEMO_MODE) {

      loadDemoData();

      return;
    }

    try {

      const statusResp =
        await fetch(
          '/api/status'
        );

      const statusData =
        await statusResp.json();

      if (datasetTag) {

        datasetTag.textContent =
          `Dataset: ${statusData.dataset_root}`;
      }

      const valResp =
        await fetch(
          '/api/validation'
        );

      if (valResp.ok) {

        const valData =
          await valResp.json();

        if (valTotalImages) {

          valTotalImages.textContent =
            valData.total_images;
        }

        if (valGpsCoverage) {

          valGpsCoverage.textContent =
            `${valData.gps_available} / ${valData.total_images}`;
        }

        if (valRtkStatus) {

          valRtkStatus.textContent =
            valData.rtk_available > 0
              ? 'Fixed (1-2cm)'
              : 'Single';
        }
      }

      const discResp =
        await fetch(
          '/api/discovery'
        );

      if (discResp.ok) {

        const discData =
          await discResp.json();

        if (valGcpCount) {

          valGcpCount.textContent =
            discData.gcp_status_summary.includes(
              'Available'
            )
              ? '5 Verified'
              : 'None';
        }
      }

      const imagesResp =
        await fetch(
          '/api/images?limit=500'
        );

      const imagesData =
        await imagesResp.json();

      if (galleryController) {

        galleryController.setRecords(
          imagesData.records || []
        );
      }

      const mapResp =
        await fetch(
          '/api/map/geojson'
        );

      const geoJsonData =
        await mapResp.json();

      if (mapController) {

        mapController.loadGeoJson(
          geoJsonData,
          (clickedId) => {

            if (galleryController) {

              galleryController.selectImage(
                clickedId
              );
            }
          }
        );
      }

      hideLoadingState();

    } catch (err) {

      console.error(
        'Failed to load dataset data:',
        err
      );

      hideLoadingState();
    }
  }

  // -----------------------------
  // Filters
  // -----------------------------
  function handleFilters() {

    if (!galleryController) return;

    galleryController.applyFilters({

      search:
        filterSearch
          ? filterSearch.value
          : '',

      gps:
        filterGps
          ? filterGps.value
          : '',

      rtk:
        filterRtk
          ? filterRtk.value
          : '',

      quality:
        filterQuality
          ? filterQuality.value
          : '',

      sortField:
        filterSort
          ? filterSort.value
          : 'image_id'
    });
  }

  if (filterSearch) {

    filterSearch.addEventListener(
      'input',
      handleFilters
    );
  }

  if (filterGps) {

    filterGps.addEventListener(
      'change',
      handleFilters
    );
  }

  if (filterRtk) {

    filterRtk.addEventListener(
      'change',
      handleFilters
    );
  }

  if (filterQuality) {

    filterQuality.addEventListener(
      'change',
      handleFilters
    );
  }

  if (filterSort) {

    filterSort.addEventListener(
      'change',
      handleFilters
    );
  }

  // -----------------------------
  // Grid / Table
  // -----------------------------
  if (
    btnViewGrid &&
    btnViewTable &&
    galleryController
  ) {

    btnViewGrid.addEventListener(
      'click',
      () => {

        btnViewGrid.classList.add(
          'active'
        );

        btnViewTable.classList.remove(
          'active'
        );

        galleryController.setView(
          'grid'
        );
      }
    );

    btnViewTable.addEventListener(
      'click',
      () => {

        btnViewTable.classList.add(
          'active'
        );

        btnViewGrid.classList.remove(
          'active'
        );

        galleryController.setView(
          'table'
        );
      }
    );
  }

  // -----------------------------
  // Map Controls
  // -----------------------------
  if (toggleTrajectory) {

    toggleTrajectory.addEventListener(
      'change',
      (e) => {

        if (mapController) {

          mapController.toggleTrajectory(
            e.target.checked
          );
        }
      }
    );
  }

  if (toggleGcps) {

    toggleGcps.addEventListener(
      'change',
      (e) => {

        if (mapController) {

          mapController.toggleGcps(
            e.target.checked
          );
        }
      }
    );
  }

  if (toggleHeading) {

    toggleHeading.addEventListener(
      'change',
      (e) => {

        if (mapController) {

          mapController.toggleHeadings(
            e.target.checked
          );
        }
      }
    );
  }

  if (btnFitBounds) {

    btnFitBounds.addEventListener(
      'click',
      () => {

        if (mapController) {

          mapController.fitBounds();
        }
      }
    );
  }

  // -----------------------------
  // Rescan
  // -----------------------------
  if (btnRefresh) {

    btnRefresh.addEventListener(
      'click',
      async () => {

        if (DEMO_MODE) {

          loadDemoData();

          return;
        }

        btnRefresh.disabled =
          true;

        btnRefresh.innerHTML =
          '<div class="spinner" style="width:14px;height:14px;border-width:2px;margin:0;"></div> Scanning...';

        try {

          await fetch(
            '/api/pipeline/run?force=true',
            {
              method: 'POST'
            }
          );

          await loadData();

        } catch (e) {

          alert(
            'Rescan failed: ' +
            e.message
          );

        } finally {

          btnRefresh.disabled =
            false;

          btnRefresh.innerHTML =
            '<i data-lucide="refresh-cw"></i> Rescan';

          lucide.createIcons();
        }
      }
    );
  }

  // -----------------------------
  // START
  // -----------------------------
  await loadData();
});
