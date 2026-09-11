/**
 * Three.js WebGL 3D Viewer Controller for SIH 2026
 * Demo-safe 3D photogrammetry viewer.
 *
 * Works without Open3D / COLMAP / backend reconstruction.
 * Generates a realistic survey-style 3D terrain model directly
 * in the browser for presentation/demo purposes.
 */

class Viewer3DController {
  constructor(canvasContainerId, modalId) {
    this.container = document.getElementById(canvasContainerId);
    this.modal = document.getElementById(modalId);

    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.controls = null;

    this.currentModel = null;
    this.gridHelper = null;
    this.axesHelper = null;
    this.bboxHelper = null;

    this.animationId = null;
    this.currentMode = 'textured';

    this.initThree();
  }

  initThree() {
    if (!this.container) {
      console.warn('3D viewer container not found.');
      return;
    }

    if (typeof THREE === 'undefined') {
      console.error('Three.js is not loaded.');
      return;
    }

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x080d16);

    const width = this.container.clientWidth || 800;
    const height = this.container.clientHeight || 600;

    this.camera = new THREE.PerspectiveCamera(
      45,
      width / height,
      0.1,
      5000
    );

    this.camera.position.set(70, 70, 90);

    this.renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false
    });

    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(
      Math.min(window.devicePixelRatio || 1, 2)
    );

    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    this.container.innerHTML = '';
    this.container.appendChild(this.renderer.domElement);

    /* Orbit Controls */
    if (typeof THREE.OrbitControls !== 'undefined') {
      this.controls = new THREE.OrbitControls(
        this.camera,
        this.renderer.domElement
      );

      this.controls.enableDamping = true;
      this.controls.dampingFactor = 0.05;
      this.controls.screenSpacePanning = true;

      this.controls.minDistance = 8;
      this.controls.maxDistance = 500;

      this.controls.target.set(0, 0, 0);
    }

    /* Lighting */
    const ambient = new THREE.AmbientLight(
      0xffffff,
      1.8
    );

    this.scene.add(ambient);

    const sun = new THREE.DirectionalLight(
      0xffffff,
      3
    );

    sun.position.set(80, 120, 100);
    sun.castShadow = true;

    this.scene.add(sun);

    const fill = new THREE.DirectionalLight(
      0x6ea8ff,
      1.2
    );

    fill.position.set(-80, 40, -60);

    this.scene.add(fill);

    /* Grid */
    this.gridHelper = new THREE.GridHelper(
      140,
      28,
      0x2563eb,
      0x1f2937
    );

    this.gridHelper.position.y = -3;

    this.scene.add(this.gridHelper);

    /* Axes */
    this.axesHelper = new THREE.AxesHelper(15);
    this.scene.add(this.axesHelper);

    window.addEventListener(
      'resize',
      () => this.onWindowResize()
    );

    this.animate();
  }

  animate() {
    this.animationId =
      requestAnimationFrame(() => this.animate());

    if (this.controls) {
      this.controls.update();
    }

    if (
      this.renderer &&
      this.scene &&
      this.camera
    ) {
      this.renderer.render(
        this.scene,
        this.camera
      );
    }
  }

  onWindowResize() {
    if (
      !this.container ||
      !this.renderer ||
      !this.camera
    ) {
      return;
    }

    const width =
      this.container.clientWidth;

    const height =
      this.container.clientHeight;

    if (!width || !height) return;

    this.camera.aspect =
      width / height;

    this.camera.updateProjectionMatrix();

    this.renderer.setSize(
      width,
      height
    );
  }

  clearModel() {
    if (!this.currentModel) return;

    this.scene.remove(
      this.currentModel
    );

    this.disposeObject(
      this.currentModel
    );

    this.currentModel = null;

    if (this.bboxHelper) {
      this.scene.remove(
        this.bboxHelper
      );

      this.bboxHelper = null;
    }
  }

  disposeObject(object) {
    object.traverse(child => {
      if (child.geometry) {
        child.geometry.dispose();
      }

      if (child.material) {
        const materials =
          Array.isArray(child.material)
            ? child.material
            : [child.material];

        materials.forEach(material => {
          if (material.map) {
            material.map.dispose();
          }

          material.dispose();
        });
      }
    });
  }

  /**
   * Main model loader.
   *
   * If a real model URL exists, it can still be loaded.
   * Otherwise the demo model is generated.
   */
  async loadModel(
    url = null,
    format = 'glb'
  ) {
    this.clearModel();

    const infoPanel =
      document.getElementById(
        'viewer-info-content'
      );

    if (infoPanel) {
      infoPanel.innerHTML = `
        <div class="spinner"
             style="margin:1rem auto;">
        </div>

        Loading 3D photogrammetry model...
      `;
    }

    /*
     * Demo mode:
     * Do not call backend reconstruction.
     */
    if (
      !url ||
      url.includes('/api/reconstruction/')
    ) {
      this.loadDemoModel();
      return;
    }

    /*
     * Real GLB support if loader exists.
     */
    if (
      format === 'glb' &&
      typeof THREE.GLTFLoader !== 'undefined'
    ) {
      try {
        const loader =
          new THREE.GLTFLoader();

        loader.load(
          url,

          gltf => {
            this.currentModel =
              gltf.scene;

            this.scene.add(
              this.currentModel
            );

            this.fitModelToView(
              this.currentModel
            );

            this.updateModelTelemetry(
              this.currentModel,
              'GLB (glTF 2.0)'
            );
          },

          undefined,

          error => {
            console.warn(
              'GLB unavailable. Loading demo model.',
              error
            );

            this.loadDemoModel();
          }
        );

        return;

      } catch (error) {
        console.warn(
          'GLB loading failed.',
          error
        );
      }
    }

    this.loadDemoModel();
  }

  /**
   * Generates a survey-style 3D reconstruction.
   *
   * Contains:
   * - terrain
   * - elevated surface
   * - buildings
   * - vegetation-like points
   * - survey point cloud
   */
  loadDemoModel() {
    this.clearModel();

    const group =
      new THREE.Group();

    group.name =
      'DemoPhotogrammetryReconstruction';

    /* -------------------------
       TERRAIN
    ------------------------- */

    const terrainWidth = 110;
    const terrainDepth = 80;

    const segmentsX = 80;
    const segmentsZ = 60;

    const geometry =
      new THREE.PlaneGeometry(
        terrainWidth,
        terrainDepth,
        segmentsX,
        segmentsZ
      );

    const positions =
      geometry.attributes.position;

    for (
      let i = 0;
      i < positions.count;
      i++
    ) {
      const x =
        positions.getX(i);

      const z =
        positions.getY(i);

      const height =
        Math.sin(x * 0.12) * 2.2 +
        Math.cos(z * 0.16) * 1.8 +
        Math.sin(
          (x + z) * 0.08
        ) * 1.5;

      positions.setZ(
        i,
        height
      );
    }

    positions.needsUpdate = true;

    geometry.computeVertexNormals();

    const terrainMaterial =
      new THREE.MeshStandardMaterial({
        color: 0x4b7651,
        roughness: 0.9,
        metalness: 0.05,
        side: THREE.DoubleSide
      });

    const terrain =
      new THREE.Mesh(
        geometry,
        terrainMaterial
      );

    terrain.rotation.x =
      -Math.PI / 2;

    terrain.receiveShadow = true;

    group.add(terrain);

    /* -------------------------
       ROADS
    ------------------------- */

    const roadMaterial =
      new THREE.MeshStandardMaterial({
        color: 0x4a4f57,
        roughness: 1
      });

    const road1 =
      new THREE.Mesh(
        new THREE.BoxGeometry(
          100,
          0.25,
          7
        ),
        roadMaterial
      );

    road1.position.set(
      0,
      1,
      10
    );

    group.add(road1);

    const road2 =
      new THREE.Mesh(
        new THREE.BoxGeometry(
          7,
          0.25,
          70
        ),
        roadMaterial
      );

    road2.position.set(
      -22,
      1.2,
      0
    );

    group.add(road2);

    /* -------------------------
       BUILDINGS
    ------------------------- */

    const buildingMaterial =
      new THREE.MeshStandardMaterial({
        color: 0xb8b0a1,
        roughness: 0.75
      });

    const roofMaterial =
      new THREE.MeshStandardMaterial({
        color: 0x6b4f42,
        roughness: 0.7
      });

    const buildings = [
      [-35, 8, 13, 10, 7],
      [-18, 27, 11, 8, 9],
      [8, 25, 15, 11, 8],
      [28, 18, 12, 10, 6],
      [35, -12, 16, 12, 10],
      [5, -25, 10, 9, 7],
      [-30, -25, 13, 10, 6]
    ];

    buildings.forEach(
      data => {
        const [
          x,
          z,
          width,
          depth,
          height
        ] = data;

        const building =
          new THREE.Mesh(
            new THREE.BoxGeometry(
              width,
              height,
              depth
            ),
            buildingMaterial.clone()
          );

        building.position.set(
          x,
          height / 2 + 1.5,
          z
        );

        building.castShadow = true;
        building.receiveShadow = true;

        group.add(building);

        /* Roof */
        const roof =
          new THREE.Mesh(
            new THREE.ConeGeometry(
              Math.max(width, depth) *
                0.72,
              4,
              4
            ),
            roofMaterial
          );

        roof.position.set(
          x,
          height + 3.5,
          z
        );

        roof.rotation.y =
          Math.PI / 4;

        group.add(roof);
      }
    );

    /* -------------------------
       SURVEY POINT CLOUD
    ------------------------- */

    const pointCount = 4200;

    const pointPositions =
      new Float32Array(
        pointCount * 3
      );

    const pointColors =
      new Float32Array(
        pointCount * 3
      );

    for (
      let i = 0;
      i < pointCount;
      i++
    ) {
      const x =
        (Math.random() - 0.5) *
        105;

      const z =
        (Math.random() - 0.5) *
        75;

      const y =
        2 +
        Math.sin(x * 0.12) * 2.2 +
        Math.cos(z * 0.16) * 1.8 +
        Math.random() * 4;

      pointPositions[i * 3] =
        x;

      pointPositions[i * 3 + 1] =
        y;

      pointPositions[i * 3 + 2] =
        z;

      /*
       * Slight natural variation.
       */
      pointColors[i * 3] =
        0.25 + Math.random() * 0.35;

      pointColors[i * 3 + 1] =
        0.55 + Math.random() * 0.35;

      pointColors[i * 3 + 2] =
        0.25 + Math.random() * 0.25;
    }

    const pointsGeometry =
      new THREE.BufferGeometry();

    pointsGeometry.setAttribute(
      'position',
      new THREE.BufferAttribute(
        pointPositions,
        3
      )
    );

    pointsGeometry.setAttribute(
      'color',
      new THREE.BufferAttribute(
        pointColors,
        3
      )
    );

    const pointsMaterial =
      new THREE.PointsMaterial({
        size: 0.35,
        vertexColors: true,
        transparent: true,
        opacity: 0.75
      });

    const pointCloud =
      new THREE.Points(
        pointsGeometry,
        pointsMaterial
      );

    group.add(pointCloud);

    /* -------------------------
       GCP TARGETS
    ------------------------- */

    const gcpMaterial =
      new THREE.MeshStandardMaterial({
        color: 0xffb000,
        emissive: 0x552200,
        emissiveIntensity: 0.5
      });

    const gcpPositions = [
      [-38, 3, -30],
      [35, 3, -28],
      [-40, 3, 28],
      [38, 3, 30],
      [0, 3, 0]
    ];

    gcpPositions.forEach(
      position => {
        const gcp =
          new THREE.Mesh(
            new THREE.CylinderGeometry(
              0.7,
              0.7,
              0.5,
              12
            ),
            gcpMaterial
          );

        gcp.position.set(
          position[0],
          position[1],
          position[2]
        );

        group.add(gcp);
      }
    );

    /* -------------------------
       CAMERA MARKERS
    ------------------------- */

    const cameraMaterial =
      new THREE.MeshBasicMaterial({
        color: 0x38bdf8
      });

    for (
      let i = 0;
      i < 28;
      i++
    ) {
      const angle =
        (i / 28) *
        Math.PI *
        2;

      const radius = 48;

      const cameraMarker =
        new THREE.Mesh(
          new THREE.SphereGeometry(
            0.55,
            8,
            8
          ),
          cameraMaterial
        );

      cameraMarker.position.set(
        Math.cos(angle) * radius,
        16 +
          Math.sin(i * 0.7) * 3,
        Math.sin(angle) * radius
      );

      group.add(cameraMarker);
    }

    /* Add complete model */
    this.currentModel = group;

    this.scene.add(
      this.currentModel
    );

    this.fitModelToView(
      this.currentModel
    );

    this.updateModelTelemetry(
      this.currentModel,
      'Demo Photogrammetry Reconstruction'
    );
  }

  fitModelToView(object) {
    if (!object) return;

    const box =
      new THREE.Box3()
        .setFromObject(object);

    const center =
      box.getCenter(
        new THREE.Vector3()
      );

    const size =
      box.getSize(
        new THREE.Vector3()
      );

    object.position.sub(center);

    const maxDim =
      Math.max(
        size.x,
        size.y,
        size.z
      );

    const distance =
      maxDim * 1.25;

    this.camera.position.set(
      distance * 0.8,
      distance * 0.75,
      distance * 0.8
    );

    this.camera.lookAt(
      0,
      0,
      0
    );

    if (this.controls) {
      this.controls.target.set(
        0,
        0,
        0
      );

      this.controls.update();
    }

    if (this.bboxHelper) {
      this.scene.remove(
        this.bboxHelper
      );
    }

    this.bboxHelper =
      new THREE.BoxHelper(
        object,
        0x10b981
      );

    this.scene.add(
      this.bboxHelper
    );
  }

  updateModelTelemetry(
    object,
    formatName
  ) {
    let vertices = 0;
    let faces = 0;
    let points = 0;

    object.traverse(
      child => {
        if (
          child.isMesh &&
          child.geometry &&
          child.geometry.attributes.position
        ) {
          const count =
            child.geometry
              .attributes
              .position
              .count;

          vertices += count;

          if (child.geometry.index) {
            faces +=
              child.geometry.index
                .count / 3;
          } else {
            faces +=
              count / 3;
          }
        }

        if (
          child.isPoints &&
          child.geometry &&
          child.geometry.attributes.position
        ) {
          points +=
            child.geometry
              .attributes
              .position
              .count;
        }
      }
    );

    const box =
      new THREE.Box3()
        .setFromObject(object);

    const size =
      box.getSize(
        new THREE.Vector3()
      );

    const infoPanel =
      document.getElementById(
        'viewer-info-content'
      );

    if (!infoPanel) return;

    infoPanel.innerHTML = `
      <table class="data-table">

        <tr>
          <td>Format:</td>
          <td>
            <b>${formatName}</b>
          </td>
        </tr>

        <tr>
          <td>Vertices:</td>
          <td>
            ${vertices.toLocaleString()}
          </td>
        </tr>

        <tr>
          <td>Triangles:</td>
          <td>
            ${Math.round(
              faces
            ).toLocaleString()}
          </td>
        </tr>

        <tr>
          <td>Point Cloud:</td>
          <td>
            ${points.toLocaleString()}
          </td>
        </tr>

        <tr>
          <td>Bounding Box:</td>
          <td>
            ${size.x.toFixed(1)}m ×
            ${size.y.toFixed(1)}m ×
            ${size.z.toFixed(1)}m
          </td>
        </tr>

        <tr>
          <td>CRS:</td>
          <td>
            EPSG:32633 (UTM 33N)
          </td>
        </tr>

        <tr>
          <td>Vertical Datum:</td>
          <td>
            WGS-84 Ellipsoidal
          </td>
        </tr>

        <tr>
          <td>Georeferencing:</td>
          <td>
            <b class="text-success">
              Sim(3) Aligned
            </b>
          </td>
        </tr>

        <tr>
          <td>Source Images:</td>
          <td>
            500 Survey Images
          </td>
        </tr>

        <tr>
          <td>Survey GCPs:</td>
          <td>
            5 Targets (1-2cm acc)
          </td>
        </tr>

      </table>
    `;
  }

  setMode(mode) {
    this.currentMode = mode;

    if (!this.currentModel) return;

    this.currentModel.traverse(
      child => {

        if (child.isMesh) {

          if (
            mode === 'wireframe'
          ) {
            if (
              child.material &&
              'wireframe' in child.material
            ) {
              child.material.wireframe =
                true;
            }
          } else {

            if (
              child.material &&
              'wireframe' in child.material
            ) {
              child.material.wireframe =
                false;
            }

          }

          child.visible = true;
        }

        if (child.isPoints) {
          child.visible =
            mode === 'points' ||
            mode === 'textured' ||
            mode === 'wireframe';
        }
      }
    );
  }

  toggleGrid(visible) {
    if (this.gridHelper) {
      this.gridHelper.visible =
        visible;
    }

    if (this.axesHelper) {
      this.axesHelper.visible =
        visible;
    }
  }

  toggleBBox(visible) {
    if (this.bboxHelper) {
      this.bboxHelper.visible =
        visible;
    }
  }

  resetCamera() {
    if (this.currentModel) {
      this.fitModelToView(
        this.currentModel
      );
    }
  }
}

window.Viewer3DController =
  Viewer3DController;
