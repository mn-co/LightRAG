import { useState, useCallback } from 'react'
import type { FocusEvent } from 'react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/Popover'
import Button from '@/components/ui/Button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select'
import { useSettingsStore } from '@/stores/settings'
import { useBackendState } from '@/stores/state'
import { PaletteIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import Input from '@/components/ui/Input'

interface AppSettingsProps {
  className?: string
}

export default function AppSettings({ className }: AppSettingsProps) {
  const [opened, setOpened] = useState<boolean>(false)
  const { t } = useTranslation()

  const language = useSettingsStore.use.language()
  const setLanguage = useSettingsStore.use.setLanguage()

  const theme = useSettingsStore.use.theme()
  const setTheme = useSettingsStore.use.setTheme()

  const workspace = useSettingsStore.use.workspace()
  const setWorkspace = useSettingsStore.use.setWorkspace()
  const workspaceRevision = useSettingsStore.use.workspaceRevision()

  const handleLanguageChange = useCallback((value: string) => {
    setLanguage(value as 'en' | 'zh' | 'fr' | 'ar' | 'zh_TW')
  }, [setLanguage])

  const handleThemeChange = useCallback((value: string) => {
    setTheme(value as 'light' | 'dark' | 'system')
  }, [setTheme])

  const handleWorkspaceBlur = useCallback((event: FocusEvent<HTMLInputElement>) => {
    const sanitized = event.target.value.replace(/[^A-Za-z0-9_-]/g, '').slice(0, 64)
    event.target.value = sanitized

    const currentWorkspace = useSettingsStore.getState().workspace
    if (sanitized !== currentWorkspace) {
      setWorkspace(sanitized)
      // Trigger an immediate backend health check to refresh configuration context
      Promise.resolve(useBackendState.getState().check()).catch(() => {})
    }
  }, [setWorkspace])

  return (
    <Popover open={opened} onOpenChange={setOpened}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className={cn('h-9 w-9', className)}>
          <PaletteIcon className="h-5 w-5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent side="bottom" align="end" className="w-56">
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium">{t('graphPanel.statusCard.workspace')}</label>
            <Input
              key={workspaceRevision}
              defaultValue={workspace}
              onBlur={handleWorkspaceBlur}
              placeholder={t('header.workspacePlaceholder')}
              maxLength={64}
              className="h-9"
              autoComplete="off"
            />
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium">{t('settings.language')}</label>
            <Select value={language} onValueChange={handleLanguageChange}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="en">English</SelectItem>
                <SelectItem value="zh">中文</SelectItem>
                <SelectItem value="fr">Français</SelectItem>
                <SelectItem value="ar">العربية</SelectItem>
                <SelectItem value="zh_TW">繁體中文</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium">{t('settings.theme')}</label>
            <Select value={theme} onValueChange={handleThemeChange}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="light">{t('settings.light')}</SelectItem>
                <SelectItem value="dark">{t('settings.dark')}</SelectItem>
                <SelectItem value="system">{t('settings.system')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}
