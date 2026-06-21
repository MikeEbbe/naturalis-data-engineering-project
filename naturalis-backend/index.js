const express = require('express');
const cors = require('cors');
const mysql = require('mysql2/promise');

const app = express();

// DB connection
const pool = mysql.createPool({
    host: '127.0.0.1',
    user: 'root',
    password: 'password',
    database: 'airflow',
    waitForConnections: true
});

// Connection test
pool.getConnection((err, connection) => {
    if (err) throw err;
    console.log('Connected to MySQL!');
    connection.release();
});

// Middleware
app.use(cors());
app.use(express.json());

/**
 * Route definition
 */
// Species search endpoint
app.post('/api/species/search', async (req, res) => {
    try {
        const { term } = req.body;
        let sql_query = 'SELECT * FROM biodiversity_data WHERE genus_or_monomial LIKE ? LIMIT 10';

        const [rows] = await pool.execute(sql_query, [`%${term}%`]); // execute query

        res.json({
            success: true,
            data: rows,
            count: rows.length,
            searchCriteria: req.body
        });
    } catch (error) {
        // failed
        console.error('Species search failed:', error);
        res.status(500).json({
            success: false,
            error: 'Species search failed'
        });
    }
});

// Health check endpoint
app.get('/api/health', (req, res) => {
    res.json({
        success: true,
        message: 'Server is running',
        timestamp: new Date().toISOString()
    });
});

// Middleware error handling
app.use((err, req, res, next) => {
    console.error(err.stack);
    res.status(500).json({
        success: false,
        error: 'Something went wrong!'
    });
});

// Start server
app.listen('3001', () => {
    console.log(`Server running on http://localhost:3001`);
    console.log('Available endpoints:');
    console.log('  GET  /api/health');
    console.log('  POST /species/search');
});

module.exports = app;
