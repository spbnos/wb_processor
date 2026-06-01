import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import CommandCenter from './pages/CommandCenter'
import MappingReview from './pages/MappingReview'
import Mappings from './pages/Mappings'
import MLInsights from './pages/MLInsights'
import Analytics from './pages/Analytics'
import ProductMatrix from './pages/ProductMatrix'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<CommandCenter />} />
          <Route path="review"   element={<MappingReview />} />
          <Route path="mappings" element={<Mappings />} />
          <Route path="ml"       element={<MLInsights />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="products"  element={<ProductMatrix />} />
          <Route path="files"    element={<CommandCenter />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
