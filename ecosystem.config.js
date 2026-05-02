module.exports = {
  apps: [
    {
      name: 'wdo-backend',
      script: 'server.py',
      interpreter: 'python',
      watch: false
    },
    {
      name: 'wdo-frontend',
      script: './node_modules/vite/bin/vite.js',
      cwd: './regime-dashboard',
      watch: false,
      env: {
        NODE_ENV: 'development'
      }
    }
  ]
};
