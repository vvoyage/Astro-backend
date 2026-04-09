import { NavLink } from 'react-router-dom';

const links = [
  { to: '/dashboard', label: 'Проекты' },
  { to: '/generate', label: 'Создать' },
];

export default function Sidebar() {
  return (
    <nav className="flex w-48 flex-col gap-1 border-r border-gray-800 p-3">
      {links.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          className={({ isActive }) =>
            `rounded px-3 py-2 text-sm transition-colors ${
              isActive ? 'bg-gray-800 text-white' : 'text-gray-400 hover:text-white'
            }`
          }
        >
          {link.label}
        </NavLink>
      ))}
    </nav>
  );
}
