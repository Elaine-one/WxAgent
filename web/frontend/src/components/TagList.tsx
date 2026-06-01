import { useState } from 'react'
import { Input, Button, Space, Tag } from 'antd'
import { PlusOutlined } from '@ant-design/icons'

interface TagListProps {
  value: string[]
  onChange: (v: string[]) => void
  disabled?: boolean
  inputWidth?: number
}

export default function TagList({ value, onChange, disabled, inputWidth = 150 }: TagListProps) {
  const [input, setInput] = useState('')

  const add = () => {
    if (disabled) return
    const v = input.trim()
    if (v && !value.includes(v)) {
      onChange([...value, v])
      setInput('')
    }
  }

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, alignItems: 'center' }}>
      {value.map((item) => (
        <Tag key={item} closable={!disabled} onClose={() => onChange(value.filter(v => v !== item))}>{item}</Tag>
      ))}
      {!disabled && (
        <Space.Compact>
          <Input size="small" value={input} onChange={e => setInput(e.target.value)} onPressEnter={add} style={{ width: inputWidth }} />
          <Button size="small" type="dashed" icon={<PlusOutlined />} onClick={add} />
        </Space.Compact>
      )}
    </div>
  )
}
