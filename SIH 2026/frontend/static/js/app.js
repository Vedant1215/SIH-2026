/**
 * Main Application Orchestrator for SIH 2026 Drone Ingestion System.
 * Coordinates data fetching, state management, map rendering, and gallery interactions.
 */

document.addEventListener('DOMContentLoaded', async () => {
  // Initialize Lucide icons
  lucide.createIcons();

  // Instantiate controllers
  let mapController = null;
  let galleryController = null;
  let viewer3dController = null;
  let reconstructController = null;

  try {
    mapController = new DroneMapController('leaflet-map');
    viewer3dController = new Viewer3DController('viewer-canvas', 'viewer-modal');
    reconstructController = new ReconstructionController(viewer3dController);
  } catch (e) {
    console.error('Initialization error:', e);
  }

  // 3D Viewer Toolbar & Modal Controls
  const btnCloseViewer = document.getElementById('btn-close-viewer');
  const viewerModal = document.getElementById('viewer-modal');
  if (btnCloseViewer && viewerModal) {
    btnCloseViewer.addEventListener('click', () => {
      viewerModal.style.display = 'none';
    });
    viewerModal.addEventListener('click', (e) => {
      if (e.target === viewerModal) viewerModal.style.display = 'none';
    });
  }

  const btnModeTextured = document.getElementById('btn-mode-textured');
  const btnModeWireframe = document.getElementById('btn-mode-wireframe');
  const btnModePoints = document.getElementById('btn-mode-points');
  const btnToggleGrid = document.getElementById('btn-toggle-grid');
  const btnToggleBBox = document.getElementById('btn-toggle-bbox');
  const btnResetCam = document.getElementById('btn-reset-cam');

  let gridVisible = true;
  let bboxVisible = true;

  if (btnModeTextured && btnModeWireframe && btnModePoints && viewer3dController) {
    btnModeTextured.addEventListener('click', () => {
      btnModeTextured.classList.add('active');
      btnModeWireframe.classList.remove('active');
      btnModePoints.classList.remove('active');
      viewer3dController.setMode('textured');
    });
    btnModeWireframe.addEventListener('click', () => {
      btnModeWireframe.classList.add('active');
      btnModeTextured.classList.remove('active');
      btnModePoints.classList.remove('active');
      viewer3dController.setMode('wireframe');
    });
    btnModePoints.addEventListener('click', () => {
      btnModePoints.classList.add('active');
      btnModeTextured.classList.remove('active');
      btnModeWireframe.classList.remove('active');
      viewer3dController.loadModel('/api/reconstruction/sparse', 'ply');
    });
  }

  if (btnToggleGrid && viewer3dController) {
    btnToggleGrid.addEventListener('click', () => {
      gridVisible = !gridVisible;
      btnToggleGrid.classList.toggle('active', gridVisible);
      viewer3dController.toggleGrid(gridVisible);
    });
  }
  if (btnToggleBBox && viewer3dController) {
    btnToggleBBox.addEventListener('click', () => {
      bboxVisible = !bboxVisible;
      btnToggleBBox.classList.toggle('active', bboxVisible);
      viewer3dController.toggleBBox(bboxVisible);
    });
  }
  if (btnResetCam && viewer3dController) {
    btnResetCam.addEventListener('click', () => {
      viewer3dController.resetCamera();
    });
  }

  galleryController = new GalleryController('gallery-container', (selectedImageId) => {
    if (mapController) {
      mapController.selectImage(selectedImageId);
    }
  });

  // UI Element References
  const valTotalImages = document.getElementById('val-total-images');
  const valGpsCoverage = document.getElementById('val-gps-coverage');
  const valRtkStatus = document.getElementById('val-rtk-status');
  const valGcpCount = document.getElementById('val-gcp-count');
  const datasetTag = document.getElementById('dataset-location-tag');

  const filterSearch = document.getElementById('filter-search');
  const filterGps = document.getElementById('filter-gps');
  const filterRtk = document.getElementById('filter-rtk');
  const filterQuality = document.getElementById('filter-quality');
  const filterSort = document.getElementById('filter-sort');

  const btnViewGrid = document.getElementById('btn-view-grid');
  const btnViewTable = document.getElementById('btn-view-table');
  const btnRefresh = document.getElementById('btn-refresh');
  const btnFitBounds = document.getElementById('btn-fit-bounds');

  const toggleTrajectory = document.getElementById('toggle-trajectory');
  const toggleGcps = document.getElementById('toggle-gcps');
  const toggleHeading = document.getElementById('toggle-heading');

  // Load all data
  async function loadData() {
    try {
      // 1. Fetch System Status & Validation
      const statusResp = await fetch('/api/status');
      const statusData = await statusResp.json();

      if (datasetTag) {
        datasetTag.textContent = `Dataset: ${statusData.dataset_root}`;
      }

      // 2. Fetch Validation Summary for Metrics Ribbon
      const valResp = await fetch('/api/validation');
      if (valResp.ok) {
        const valData = await valResp.json();
        if (valTotalImages) valTotalImages.textContent = valData.total_images;
        if (valGpsCoverage) {
          valGpsCoverage.textContent = `${valData.gps_available} / ${valData.total_images}`;
        }
        if (valRtkStatus) {
          valRtkStatus.textContent = valData.rtk_available > 0 ? 'Fixed (1-2cm)' : 'Single';
        }
      }

      // 3. Fetch Discovery for GCP Count
      const discResp = await fetch('/api/discovery');
      if (discResp.ok) {
        const discData = await discResp.json();
        if (valGcpCount) {
          valGcpCount.textContent = discData.gcp_status_summary.includes('Available') ? '5 Verified' : 'None';
        }
      }

      // 4. Fetch All Normalized Images
      const imagesResp = await fetch('/api/images?limit=500');
      const imagesData = await imagesResp.json();
      galleryController.setRecords(imagesData.records || []);

      // 5. Fetch GeoJSON and load into map
      const mapResp = await fetch('/api/map/geojson');
      const geoJsonData = await mapResp.json();
      if (mapController) {
        mapController.loadGeoJson(geoJsonData, (clickedId) => {
          galleryController.selectImage(clickedId);
        });
      }

    } catch (err) {
      console.error('Failed to load dataset data:', err);
    }
  }

  // Filter change dispatcher
  function handleFilters() {
    galleryController.applyFilters({
      search: filterSearch ? filterSearch.value : '',
      gps: filterGps ? filterGps.value : '',
      rtk: filterRtk ? filterRtk.value : '',
      quality: filterQuality ? filterQuality.value : '',
      sortField: filterSort ? filterSort.value : 'image_id',
    });
  }

  if (filterSearch) filterSearch.addEventListener('input', handleFilters);
  if (filterGps) filterGps.addEventListener('change', handleFilters);
  if (filterRtk) filterRtk.addEventListener('change', handleFilters);
  if (filterQuality) filterQuality.addEventListener('change', handleFilters);
  if (filterSort) filterSort.addEventListener('change', handleFilters);

  // View Switchers
  if (btnViewGrid && btnViewTable) {
    btnViewGrid.addEventListener('click', () => {
      btnViewGrid.classList.add('active');
      btnViewTable.classList.remove('active');
      galleryController.setView('grid');
    });
    btnViewTable.addEventListener('click', () => {
      btnViewTable.classList.add('active');
      btnViewGrid.classList.remove('active');
      galleryController.setView('table');
    });
  }

  // Map Layer Toggles
  if (toggleTrajectory) {
    toggleTrajectory.addEventListener('change', (e) => {
      if (mapController) mapController.toggleTrajectory(e.target.checked);
    });
  }
  if (toggleGcps) {
    toggleGcps.addEventListener('change', (e) => {
      if (mapController) mapController.toggleGcps(e.target.checked);
    });
  }
  if (toggleHeading) {
    toggleHeading.addEventListener('change', (e) => {
      if (mapController) mapController.toggleHeadings(e.target.checked);
    });
  }
  if (btnFitBounds) {
    btnFitBounds.addEventListener('click', () => {
      if (mapController) mapController.fitBounds();
    });
  }

  // Rescan dataset button
  if (btnRefresh) {
    btnRefresh.addEventListener('click', async () => {
      btnRefresh.disabled = true;
      btnRefresh.innerHTML = '<div class="spinner" style="width: 14px; height: 14px; border-width: 2px; margin: 0;"></div> Scanning...';
      try {
        await fetch('/api/pipeline/run?force=true', { method: 'POST' });
        await loadData();
      } catch (e) {
        alert('Rescan failed: ' + e.message);
      } finally {
        btnRefresh.disabled = false;
        btnRefresh.innerHTML = '<i data-lucide="refresh-cw"></i> Rescan';
        lucide.createIcons();
      }
    });
  }

  // Initial data load
  await loadData();
});
