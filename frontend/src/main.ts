import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  ElAlert,
  ElAvatar,
  ElButton,
  ElCheckbox,
  ElCollapse,
  ElCollapseItem,
  ElDatePicker,
  ElDialog,
  ElDrawer,
  ElDropdown,
  ElDropdownItem,
  ElDropdownMenu,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElInputNumber,
  ElOption,
  ElPagination,
  ElResult,
  ElSelect,
  ElSkeleton,
  ElSwitch,
  ElTable,
  ElTableColumn,
  ElTag,
  ElTimeSelect,
  ElTooltip
} from 'element-plus'
import 'element-plus/dist/index.css'
import './styles.css'
import { initializeTheme } from './composables/useTheme'
import App from './App.vue'
import router from './router'

initializeTheme()

const app = createApp(App)
app.use(createPinia())
app.use(router)
for (const component of [
  ElAlert,
  ElAvatar,
  ElButton,
  ElCheckbox,
  ElCollapse,
  ElCollapseItem,
  ElDatePicker,
  ElDialog,
  ElDrawer,
  ElDropdown,
  ElDropdownItem,
  ElDropdownMenu,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElInputNumber,
  ElOption,
  ElPagination,
  ElResult,
  ElSelect,
  ElSkeleton,
  ElSwitch,
  ElTable,
  ElTableColumn,
  ElTag,
  ElTimeSelect,
  ElTooltip
]) app.use(component)
app.mount('#app')
