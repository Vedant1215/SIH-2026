/**
 * Main Application Orchestrator for SIH 2026 Drone Ingestion System.
 * DEMO MODE — lightweight prototype for Vercel presentation.
 */

document.addEventListener('DOMContentLoaded', async () => {
  lucide.createIcons();

  const DEMO_MODE = true;

  let mapController = null;
  let galleryController = null;
  let viewer3dController = null;
  let reconstructController = null;

  // Controllers
  try {
    mapController = new DroneMapController('leaflet-map');
    galleryController = new GalleryController('gallery-container', (selectedImageId) => {
      if (mapController) mapController.selectImage(selectedImageId);
    });

    if (!DEMO_MODE) {
      viewer3dController = new Viewer3DController('viewer-canvas', 'viewer-modal');
      reconstructController = new ReconstructionController(viewer3dController);
    }
  } catch (e) {
    console.error('Initialization error:', e);
  }

  // Viewer controls
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

  if (viewer3dController) {
    if (btnModeTextured && btnModeWireframe && btnModePoints) {
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
        viewer3dController.setMode('points');
      });

      btnModePoints.addEventListener('click', () => {
        btnModePoints.classList.add('active');
        btnModeTextured.classList.remove('active');
        btnModeWireframe.classList.remove('active');
        viewer3dController.loadModel('/api/reconstruction/sparse', 'ply');
      });
    }

    if (btnToggleGrid) {
      btnToggleGrid.addEventListener('click', () => {
        gridVisible = !gridVisible;
        btnToggleGrid.classList.toggle('active', gridVisible);
        viewer3dController.toggleGrid(gridVisible);
      });
    }

    if (btnToggleBBox) {
      btnToggleBBox.addEventListener('click', () => {
        bboxVisible = !bboxVisible;
        btnToggleBBox.classList.toggle('active', bboxVisible);
        viewer3dController.toggleBBox(bboxVisible);
      });
    }

    if (btnResetCam) {
      btnResetCam.addEventListener('click', () => {
        viewer3dController.resetCamera();
      });
    }
  }

  // UI references
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

  // Hide loading overlays/messages
  function hideLoadingState() {
    document.querySelectorAll('*').forEach((el) => {
      if (
        el.children.length === 0 &&
        el.textContent &&
        el.textContent.trim().toLowerCase().includes('ingesting and analyzing dataset')
      ) {
        const parent = el.closest(
          '.loading-overlay, .loading, .loader, .overlay, .modal, .status'
        );

        if (parent) {
          parent.style.display = 'none';
        } else {
          el.style.display = 'none';
        }
      }
    });
  }

  // Demo data
  function loadDemoData() {
    if (valTotalImages) valTotalImages.textContent = '500';

    if (valGpsCoverage) {
      valGpsCoverage.textContent = '500 / 500';
    }

    if (valRtkStatus) {
      valRtkStatus.textContent = 'Fixed (1-2cm)';
    }

    if (valGcpCount) {
      valGcpCount.textContent = '5 Verified';
    }

    if (datasetTag) {
      datasetTag.textContent = 'Dataset: SIH 2026 Demo Dataset';
    }

    hideLoadingState();

    console.log('SIH 2026 Demo Mode active');
  }

  // Load data
  async function loadData() {
    if (DEMO_MODE) {
      loadDemoData();
      return;
    }

    try {
      const statusResp = await fetch('/api/status');
      const statusData = await statusResp.json();

      if (datasetTag) {
        datasetTag.textContent = `Dataset: ${statusData.dataset_root}`;
      }

      const valResp = await fetch('/api/validation');

      if (valResp.ok) {
        const valData = await valResp.json();

        if (valTotalImages) {
          valTotalImages.textContent = valData.total_images;
        }

        if (valGpsCoverage) {
          valGpsCoverage.textContent =
            `${valData.gps_available} / ${valData.total_images}`;
        }

        if (valRtkStatus) {
          valRtkStatus.textContent =
            valData.rtk_available > 0 ? 'Fixed (1-2cm)' : 'Single';
        }
      }

      const discResp = await fetch('/api/discovery');

      if (discResp.ok) {
        const discData = await discResp.json();

        if (valGcpCount) {
          valGcpCount.textContent =
            discData.gcp_status_summary.includes('Available')
              ? '5 Verified'
              : 'None';
        }
      }

      const imagesResp = await fetch('/api/images?limit=500');
      const imagesData = await imagesResp.json();

      if (galleryController) {
        galleryController.setRecords(imagesData.records || []);
      }

      const mapResp = await fetch('/api/map/geojson');
      const geoJsonData = await mapResp.json();

      if (mapController) {
        mapController.loadGeoJson(geoJsonData, (clickedId) => {
          galleryController.selectImage(clickedId);
        });
      }

      hideLoadingState();

    } catch (err) {
      console.error('Failed to load dataset data:', err);
      hideLoadingState();
    }
  }

  // Filters
  function handleFilters() {
    if (!galleryController) return;

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

  // View switchers
  if (btnViewGrid && btnViewTable && galleryController) {
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

  // Map toggles
  if (toggleTrajectory) {
    toggleTrajectory.addEventListener('change', (e) => {
      if (mapController) {
        mapController.toggleTrajectory(e.target.checked);
      }
    });
  }

  if (toggleGcps) {
    toggleGcps.addEventListener('change', (e) => {
      if (mapController) {
        mapController.toggleGcps(e.target.checked);
      }
    });
  }

  if (toggleHeading) {
    toggleHeading.addEventListener('change', (e) => {
      if (mapController) {
        mapController.toggleHeadings(e.target.checked);
      }
    });
  }

  if (btnFitBounds) {
    btnFitBounds.addEventListener('click', () => {
      if (mapController) {
        mapController.fitBounds();
      }
    });
  }

  // Rescan button
  if (btnRefresh) {
    btnRefresh.addEventListener('click', async () => {
      if (DEMO_MODE) {
        loadDemoData();
        return;
      }

      btnRefresh.disabled = true;

      btnRefresh.innerHTML =
        '<div class="spinner" style="width: 14px; height: 14px; border-width: 2px; margin: 0;"></div> Scanning...';

      try {
        await fetch('/api/pipeline/run?force=true', {
          method: 'POST'
        });

        await loadData();

      } catch (e) {
        alert('Rescan failed: ' + e.message);

      } finally {
        btnRefresh.disabled = false;

        btnRefresh.innerHTML =
          '<i data-lucide="refresh-cw"></i> Rescan';

        lucide.createIcons();
      }
    });
  }

  // Initial load
  await loadData();
});
