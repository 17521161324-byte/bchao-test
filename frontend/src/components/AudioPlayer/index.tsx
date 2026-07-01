/**
 * 音频播放器组件 - 支持 seg 切换与自动连播
 */
import React, { useState, useRef, useEffect } from 'react'
import { Button, Slider, Space, Tag } from 'antd'
import {
  CaretRightOutlined,
  PauseOutlined,
  StepBackwardOutlined,
  StepForwardOutlined,
} from '@ant-design/icons'
import { AudioSeg } from '../../types'

interface AudioPlayerProps {
  segs: AudioSeg[]
  currentSegIndex?: number
  onSegChange?: (index: number) => void
  highlightSegIndex?: number // 当前正在转写的 seg（高亮）
}

export default function AudioPlayer({
  segs,
  currentSegIndex: externalIndex,
  onSegChange,
  highlightSegIndex,
}: AudioPlayerProps) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const audioRef = useRef<HTMLAudioElement>(null)

  const activeIndex = externalIndex ?? currentIndex
  const currentSeg = segs[activeIndex]

  useEffect(() => {
    if (audioRef.current && currentSeg) {
      audioRef.current.src = `/api/audio/file?path=${encodeURIComponent(currentSeg.file_path)}`
      audioRef.current.load()
      if (isPlaying) audioRef.current.play()
    }
  }, [activeIndex, currentSeg?.file_path])

  const handlePlayPause = () => {
    if (!audioRef.current) return
    if (isPlaying) {
      audioRef.current.pause()
    } else {
      audioRef.current.play()
    }
    setIsPlaying(!isPlaying)
  }

  const goToSeg = (index: number) => {
    if (index < 0 || index >= segs.length) return
    setCurrentIndex(index)
    onSegChange?.(index)
    setIsPlaying(true)
  }

  const handleEnded = () => {
    if (activeIndex < segs.length - 1) {
      goToSeg(activeIndex + 1)
    } else {
      setIsPlaying(false)
    }
  }

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60)
    const s = Math.floor(seconds % 60)
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  if (!segs.length) {
    return <div style={{ padding: 16, color: '#999' }}>无音频</div>
  }

  return (
    <div style={{ padding: 16, background: '#fafafa', borderRadius: 8, border: '1px solid #f0f0f0' }}>
      <audio
        ref={audioRef}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onEnded={handleEnded}
        onTimeUpdate={(e) => {
          const audio = e.currentTarget
          if (audio.duration) {
            setProgress((audio.currentTime / audio.duration) * 100)
          }
        }}
        style={{ display: 'none' }}
      />

      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <Tag color="blue">第 {activeIndex + 1} / {segs.length} 段</Tag>
          {currentSeg && <span style={{ color: '#666', fontSize: 12 }}>{currentSeg.filename}</span>}
        </Space>
        {highlightSegIndex !== undefined && highlightSegIndex !== activeIndex && (
          <Tag color="processing">正在转写第 {highlightSegIndex + 1} 段...</Tag>
        )}
      </div>

      <Slider value={progress} onChange={() => {}} tooltip={{ formatter: null }} />

      <div style={{ textAlign: 'center', marginTop: 8 }}>
        <Space size="large">
          <Button
            icon={<StepBackwardOutlined />}
            disabled={activeIndex === 0}
            onClick={() => goToSeg(activeIndex - 1)}
          />
          <Button
            type="primary"
            shape="circle"
            size="large"
            icon={isPlaying ? <PauseOutlined /> : <CaretRightOutlined />}
            onClick={handlePlayPause}
          />
          <Button
            icon={<StepForwardOutlined />}
            disabled={activeIndex === segs.length - 1}
            onClick={() => goToSeg(activeIndex + 1)}
          />
        </Space>
      </div>

      {/* seg 快捷列表 */}
      <div style={{ marginTop: 12, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {segs.map((seg, idx) => (
          <Button
            key={seg.id}
            size="small"
            type={idx === activeIndex ? 'primary' : (idx === highlightSegIndex ? 'dashed' : 'default')}
            onClick={() => goToSeg(idx)}
          >
            {idx + 1}
          </Button>
        ))}
      </div>
    </div>
  )
}
