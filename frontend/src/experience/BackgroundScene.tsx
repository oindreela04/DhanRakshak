import { useMemo, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { scroll } from './scroll'

const COINS = 260

/** Shield: faceted wireframe shell around a glowing core, the brand's "guardian". */
function Shield() {
  const group = useRef<THREE.Group>(null!)
  const shell = useRef<THREE.Mesh>(null!)
  const core = useRef<THREE.Mesh>(null!)
  const ring = useRef<THREE.Mesh>(null!)
  const coreMat = useRef<THREE.MeshStandardMaterial>(null!)
  const jade = useMemo(() => new THREE.Color('#38d6b0'), [])
  const saffron = useMemo(() => new THREE.Color('#f4b740'), [])
  useFrame((state, dt) => {
    const p = scroll.progress
    const g = group.current
    g.rotation.y += dt * (0.18 + scroll.velocity * 4)
    shell.current.rotation.x += dt * 0.12
    ring.current.rotation.z -= dt * 0.4
    // glide: centre-right on hero, drifts left & recedes as you scroll
    const k = Math.min(1, p * 5) // hero → rest of page
    const tx = THREE.MathUtils.lerp(1.9, 4.6 + Math.sin(p * Math.PI * 2) * 0.8, k)
    const ty = THREE.MathUtils.lerp(0, -1.2 + Math.sin(p * Math.PI * 3) * 1.2, k) - p * 1.5
    const tz = THREE.MathUtils.lerp(0, -6, k)
    g.position.lerp(new THREE.Vector3(tx + state.pointer.x * 0.25, ty + state.pointer.y * 0.2, tz), 0.06)
    const pulse = 1 + Math.sin(state.clock.elapsedTime * 2.2) * 0.04
    core.current.scale.setScalar(pulse)
    coreMat.current.emissive.copy(jade).lerp(saffron, Math.min(1, p * 1.4))
  })
  return (
    <group ref={group}>
      <mesh ref={shell}>
        <icosahedronGeometry args={[1.55, 1]} />
        <meshBasicMaterial color="#38d6b0" wireframe transparent opacity={0.55} />
      </mesh>
      <mesh>
        <icosahedronGeometry args={[1.5, 1]} />
        <meshStandardMaterial color="#0b2a2d" metalness={0.6} roughness={0.25} transparent opacity={0.35} flatShading />
      </mesh>
      <mesh ref={core}>
        <sphereGeometry args={[0.55, 48, 48]} />
        <meshStandardMaterial ref={coreMat} color="#0d1f22" emissive="#38d6b0" emissiveIntensity={2.4} />
      </mesh>
      <mesh ref={ring} rotation={[Math.PI / 2.4, 0, 0]}>
        <torusGeometry args={[2.25, 0.012, 8, 160]} />
        <meshBasicMaterial color="#f4b740" />
      </mesh>
    </group>
  )
}

/** Gold coins spiralling inward — revenue being pulled back to safety. */
function CoinVortex() {
  const mesh = useRef<THREE.InstancedMesh>(null!)
  const dummy = useMemo(() => new THREE.Object3D(), [])
  const seeds = useMemo(() => Array.from({ length: COINS }, () => ({ r: 2.6 + Math.random() * 6, a: Math.random() * Math.PI * 2, y: (Math.random() - 0.5) * 9, s: 0.15 + Math.random() * 0.35, spin: Math.random() * 6 })), [])
  useFrame((state, dt) => {
    const speed = 0.15 + scroll.velocity * 12
    seeds.forEach((c, i) => {
      c.a += dt * speed * (1.6 / c.r)
      c.r -= dt * (0.08 + scroll.velocity * 3)
      if (c.r < 1.9) { c.r = 8.5; c.y = (Math.random() - 0.5) * 9 }
      dummy.position.set(Math.cos(c.a) * c.r, c.y + Math.sin(state.clock.elapsedTime * 0.6 + i) * 0.15 - scroll.progress * 4, Math.sin(c.a) * c.r - 2)
      dummy.rotation.set(c.spin + state.clock.elapsedTime, c.a, 0.4)
      dummy.scale.setScalar(c.s)
      dummy.updateMatrix()
      mesh.current.setMatrixAt(i, dummy.matrix)
    })
    mesh.current.instanceMatrix.needsUpdate = true
  })
  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, COINS]}>
      <cylinderGeometry args={[0.32, 0.32, 0.05, 28]} />
      <meshStandardMaterial color="#f4b740" metalness={0.95} roughness={0.22} emissive="#5a3a00" emissiveIntensity={0.4} />
    </instancedMesh>
  )
}

function Dust() {
  const pts = useRef<THREE.Points>(null!)
  const geo = useMemo(() => {
    const g = new THREE.BufferGeometry(); const n = 1800; const arr = new Float32Array(n * 3)
    for (let i = 0; i < n; i++) { arr[i * 3] = (Math.random() - 0.5) * 40; arr[i * 3 + 1] = (Math.random() - 0.5) * 40; arr[i * 3 + 2] = -Math.random() * 30 }
    g.setAttribute('position', new THREE.BufferAttribute(arr, 3)); return g
  }, [])
  useFrame((_, dt) => { pts.current.rotation.y += dt * 0.01; pts.current.position.y = scroll.progress * 6 })
  return <points ref={pts} geometry={geo}><pointsMaterial size={0.035} color="#7fe8d2" transparent opacity={0.55} sizeAttenuation /></points>
}

function Rig() {
  const { camera } = useThree()
  useFrame((state) => {
    camera.position.x += (state.pointer.x * 0.6 - camera.position.x) * 0.04
    camera.position.y += (state.pointer.y * 0.4 - scroll.progress * 1.5 - camera.position.y) * 0.04
    camera.lookAt(0, -scroll.progress * 1.5, -2)
  })
  return null
}

export default function BackgroundScene() {
  return (
    <div className="bg-canvas" aria-hidden>
      <Canvas camera={{ position: [0, 0, 7.5], fov: 50 }} dpr={[1, 1.75]} gl={{ antialias: true, powerPreference: 'high-performance' }}>
        <color attach="background" args={['#050d0f']} />
        <fog attach="fog" args={['#050d0f', 7, 22]} />
        <ambientLight intensity={0.35} />
        <pointLight position={[4, 4, 5]} intensity={60} color="#f4b740" />
        <pointLight position={[-5, -2, 3]} intensity={40} color="#38d6b0" />
        <Shield />
        <CoinVortex />
        <Dust />
        <Rig />
      </Canvas>
    </div>
  )
}
