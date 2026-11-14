import { useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, type ThreeEvent } from '@react-three/fiber'
import { Html, Line, OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { inr, pct, riskColor, type ScoredCustomer } from './data'

type Props = { customers: ScoredCustomer[]; selected: string | null; onSelect: (id: string) => void }

function place(c: ScoredCustomer) {
  const x = (Math.log10(Math.max(300, c.lifetime_value)) - 3.9) * 3.4
  const y = (c.risk_score - 0.52) * 10
  const z = (Math.log10(Math.max(300, c.open_amount)) - 3.5) * 3.4
  const size = 0.07 + Math.min(0.22, Math.log10(Math.max(300, c.open_amount)) * 0.035 - 0.08)
  return { pos: new THREE.Vector3(x, y, z), size }
}

function Star({ c, active, hovered, onHover, onSelect }: { c: ScoredCustomer; active: boolean; hovered: boolean; onHover: (id: string | null) => void; onSelect: (id: string) => void }) {
  const ref = useRef<THREE.Mesh>(null!)
  const { pos, size } = useMemo(() => place(c), [c])
  const color = useMemo(() => new THREE.Color(riskColor(c.risk_score)), [c.risk_score])
  useFrame((state) => {
    const target = active ? 2.4 : hovered ? 1.8 : 1 + Math.sin(state.clock.elapsedTime * 2 + pos.x * 3) * 0.06
    ref.current.scale.lerp(new THREE.Vector3(target, target, target), 0.15)
  })
  return (
    <mesh ref={ref} position={pos}
      onPointerOver={(e: ThreeEvent<PointerEvent>) => { e.stopPropagation(); onHover(c.customer_id); document.body.style.cursor = 'pointer' }}
      onPointerOut={() => { onHover(null); document.body.style.cursor = '' }}
      onClick={(e: ThreeEvent<MouseEvent>) => { e.stopPropagation(); onSelect(c.customer_id) }}>
      <sphereGeometry args={[size, 18, 18]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={active ? 2.5 : hovered ? 1.6 : 0.7} roughness={0.3} />
      {(hovered || active) && (
        <Html distanceFactor={9} position={[0, size + 0.25, 0]} center zIndexRange={[20, 0]}>
          <div className="star-tip"><b>{c.name}</b><span>{c.city} · {c.segment}</span><span>Risk <em style={{ color: riskColor(c.risk_score) }}>{pct(c.risk_score, 0)}</em> · {inr(c.open_amount)}</span></div>
        </Html>
      )}
    </mesh>
  )
}

function Axes() {
  return (
    <group>
      <gridHelper args={[12, 12, '#173b40', '#0f2a2e']} position={[0, -4.2, 0]} />
      <Line points={[[-5, -4.2, -5], [5, -4.2, -5]]} color="#2c6a70" lineWidth={1.5} />
      <Line points={[[-5, -4.2, -5], [-5, 4.2, -5]]} color="#2c6a70" lineWidth={1.5} />
      <Line points={[[-5, -4.2, -5], [-5, -4.2, 5]]} color="#2c6a70" lineWidth={1.5} />
      <Html position={[5.3, -4.2, -5]} center><span className="axis-label">lifetime value →</span></Html>
      <Html position={[-5, 4.6, -5]} center><span className="axis-label">↑ risk of loss</span></Html>
      <Html position={[-5.4, -4.2, 4.5]} center><span className="axis-label">open amount ↗</span></Html>
    </group>
  )
}

export default function RiskGalaxy({ customers, selected, onSelect }: Props) {
  const [hovered, setHovered] = useState<string | null>(null)
  return (
    <Canvas camera={{ position: [7.5, 2.8, 9], fov: 45 }} dpr={[1, 1.75]} onPointerMissed={() => setHovered(null)}>
      <color attach="background" args={['#061214']} />
      <fog attach="fog" args={['#061214', 14, 30]} />
      <ambientLight intensity={0.5} />
      <pointLight position={[6, 8, 6]} intensity={80} color="#ffffff" />
      <Axes />
      {customers.map((c) => <Star key={c.customer_id} c={c} active={selected === c.customer_id} hovered={hovered === c.customer_id} onHover={setHovered} onSelect={onSelect} />)}
      <OrbitControls enablePan={false} enableZoom minDistance={6} maxDistance={22} autoRotate={!hovered} autoRotateSpeed={0.45} enableDamping makeDefault />
    </Canvas>
  )
}
