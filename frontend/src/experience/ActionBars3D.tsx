import { useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Html, OrbitControls, RoundedBox } from '@react-three/drei'
import * as THREE from 'three'
import { label, pct, type ActionScore } from './data'

const H = 5
const SHORT: Record<string, string> = { retry: 'Retry', delayed_retry: 'Delay', payment_link: 'Link', whatsapp: 'WhatsApp', sms: 'SMS', email: 'Email', promise_to_pay: 'Promise', human_escalation: 'Human', no_action: 'Nothing' }

function Bar({ a, i, n, best }: { a: ActionScore; i: number; n: number; best: boolean }) {
  const ref = useRef<THREE.Group>(null!)
  const x = (i - (n - 1) / 2) * 1.12
  useFrame(() => {
    const target = Math.max(0.02, a.recovery_probability)
    ref.current.scale.y += (target - ref.current.scale.y) * 0.12
  })
  const color = best ? '#f4b740' : a.uplift_vs_organic > 0 ? '#38d6b0' : '#3b5a60'
  return (
    <group position={[x, 0, 0]}>
      <group ref={ref} scale={[1, 0.02, 1]}>
        <RoundedBox args={[0.72, H, 0.72]} radius={0.06} position={[0, H / 2, 0]}>
          <meshStandardMaterial color={color} emissive={color} emissiveIntensity={best ? 0.9 : 0.35} metalness={0.4} roughness={0.35} />
        </RoundedBox>
      </group>
      <Html position={[0, -0.45, 0.4]} center distanceFactor={8}><div className={best ? 'bar-label best' : 'bar-label'}>{SHORT[a.action] ?? label(a.action)}<b>{pct(a.recovery_probability, 0)}</b></div></Html>
    </group>
  )
}

export default function ActionBars3D({ actions, organic }: { actions: ActionScore[]; organic: number }) {
  const order = ['retry', 'delayed_retry', 'payment_link', 'whatsapp', 'sms', 'email', 'promise_to_pay', 'human_escalation', 'no_action']
  const sorted = order.map((name) => actions.find((a) => a.action === name)).filter(Boolean) as ActionScore[]
  const best = actions[0]?.action
  return (
    <Canvas camera={{ position: [0, 4.2, 9.5], fov: 45 }} dpr={[1, 1.75]}>
      <ambientLight intensity={0.5} />
      <directionalLight position={[4, 8, 6]} intensity={2.2} />
      <pointLight position={[-6, 3, 4]} intensity={30} color="#38d6b0" />
      <group position={[0, -1.6, 0]}>
        {sorted.map((a, i) => <Bar key={a.action} a={a} i={i} n={sorted.length} best={a.action === best} />)}
        <mesh position={[0, organic * H, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[10.4, 1.6]} />
          <meshBasicMaterial color="#f04c3e" transparent opacity={0.18} side={THREE.DoubleSide} />
        </mesh>
        <Html position={[5.5, organic * H, 0]} center distanceFactor={8}><div className="organic-tag">do nothing {pct(organic, 0)}</div></Html>
        <mesh rotation={[-Math.PI / 2, 0, 0]}><planeGeometry args={[11, 3]} /><meshStandardMaterial color="#0a1c1f" /></mesh>
      </group>
      <OrbitControls enablePan={false} enableZoom={false} minPolarAngle={0.6} maxPolarAngle={1.45} minAzimuthAngle={-0.8} maxAzimuthAngle={0.8} enableDamping />
    </Canvas>
  )
}
