// Imports
import * as d3 from 'https://cdn.skypack.dev/d3@7';
import { feature } from 'https://cdn.skypack.dev/topojson-client@3';
import { searchSpecies } from './api';
import 'fslightbox';

// Global variables
const canvas = document.getElementById('globe-canvas');
let currentPins = [];
let selectedResultIndex = 0;
let searchResults = [];

/**
 * Renders an interactive 3D globe on a canvas
 */
class CanvasGlobe {
    /**
     * Initializes the globe
     * @param {HTMLCanvasElement} el - Canvas element that contains the globe
     */
    constructor(el) {
        this.size = 600;
        this.padding = 0;
        this.x = 0;
        this.y = 0;
        this.drag = false;

        this.canvas = d3
            .select(el)
            .attr('height', this.size)
            .attr('width', this.size)
            .node();

        this.context = this.canvas.getContext('2d');
        this.context.lineWidth = 0.25;
        this.context.fillStyle = '#ffffee';
        this.context.strokeStyle = '#000';

        this.projection = d3.geoOrthographic()
            .scale(this.size / 2 - this.padding)
            .translate([this.size / 2, this.size / 2]);

        this.path = d3.geoPath().context(this.context);

        // Globe rotation when dragging the mouse
        d3.select(this.canvas).on('mousedown', () => {
            this.drag = true;
        });
        d3.select(window).on('mousemove', (event) => {
            if (!this.drag) return;
            const target = [
                0.25 * event.movementX + this.x,
                -0.25 * event.movementY + this.y
            ];
            this.render(...target);
        });
        d3.select(window).on('mouseup mouseleave', () => {
            this.drag = false;
        });
    }

    // Process Geographical JSON data of the world to display it as a map on the globe
    createWorldElements(data) {
        this.geojson = feature(data, data.objects.countries);
        this.render();
    }

    // Move the globe's rotation to a target longitude and latitude
    panTo(target) {
        const interpolator = d3.interpolateArray([this.x, this.y], target);
        // Smooth transition
        const ease = d3.easeBackOut.overshoot(3);
        const transition = d3
            .transition()
            .duration(1000)
            .ease(ease);

        transition.tween("render", () => t => {
            this.render(...interpolator(t));
        });
    }

    // Initiate a pan to specific coordinates 
    jumpToCoordinates(longitude, latitude) {
        const targetRotation = [-longitude, -latitude];
        this.panTo(targetRotation);
    }

    // Removes existing pins and adds new ones based on the search result
    updatePins() {
        currentPins.forEach(pin => pin.remove());
        currentPins = [];

        if (!searchResults.length) return;

        searchResults.forEach((result, index) => {
            const pin = this.createPin(result, index);
            currentPins.push(pin);
        });
    }

    // Creates an HTML element for a pin 
    createPin(result, index) {
        const pin = document.createElement('div');
        pin.className = `pin ${index === selectedResultIndex ? 'selected' : ''}`;
        pin.dataset.index = index;

        // Attach a click handler
        pin.addEventListener('click', () => {
            selectResult(index);
        });

        document.getElementById('globe-container').appendChild(pin);
        this.positionPin(pin, result.longitude, result.latitude);

        return pin;
    }

    // Positions a pin on the globe based on the coordinates of the result
    positionPin(pinElement, longitude, latitude) {
        const projected = this.projection([longitude, latitude]);

        if (!projected) {
            pinElement.style.display = 'none';
            return;
        }

        const [x, y] = projected;
        const rotated = d3.geoRotation(this.projection.rotate())([longitude, latitude]);
        // Check if the pin is visible
        const visible = rotated[0] >= -90 && rotated[0] <= 90;

        if (!visible) {
            pinElement.style.display = 'none';
            return;
        }

        const canvasRect = this.canvas.getBoundingClientRect();
        const containerRect = this.canvas.parentElement.getBoundingClientRect();

        const pinX = x + (canvasRect.left - containerRect.left);
        const pinY = y + (canvasRect.top - containerRect.top);

        pinElement.style.left = `${pinX}px`;
        pinElement.style.top = `${pinY}px`;
        pinElement.style.display = 'block';
    }

    // Renders the globe and its contents
    render(x = 0, y = 0) {
        y = y < -90 ? -90 : y > 90 ? 90 : y;
        x = x % 360;
        this.x = x;
        this.y = y;

        this.projection.rotate([x, y, 0]);
        this.path.projection(this.projection);

        this.context.clearRect(0, 0, this.canvas.width, this.canvas.height);

        // Draw ocean
        this.context.fillStyle = '#4A90E2';
        this.context.beginPath();
        this.context.arc(
            this.size / 2,
            this.size / 2,
            this.size / 2 - this.padding,
            0,
            2 * Math.PI
        );
        this.context.fill();

        // Draw grid (graticule is apparently the name)
        this.context.strokeStyle = 'rgba(255,255,255,0.2)';
        this.context.lineWidth = 0.5;
        this.context.beginPath();
        this.path(d3.geoGraticule()());
        this.context.stroke();

        // Draw countries
        this.context.fillStyle = '#52C41A';
        this.context.strokeStyle = '#389E0D';
        this.context.lineWidth = 0.5;
        this.context.beginPath();
        this.path({ type: 'FeatureCollection', features: this.geojson.features });
        this.context.fill();
        this.context.stroke();

        // Update pin positions
        currentPins.forEach((pin, index) => {
            if (searchResults[index]) {
                this.positionPin(pin, searchResults[index].longitude, searchResults[index].latitude);
            }
        });
    }
}

const world = new CanvasGlobe(canvas);

// Load world data
const url = 'https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json';
d3.json(url).then((data) => {
    world.createWorldElements(data);
}).catch((error) => {
    console.error('Error loading world data:', error);
});

/**
 * Performs a search for a term to the search species API route
 * @param {string} term - The search term to process
 */
async function performSpeciesSearch(term) {
    try {
        const searchButton = document.getElementById('search-button');
        const errorContainer = document.getElementById('error-container');

        searchButton.disabled = true;
        searchButton.textContent = 'Searching...';
        errorContainer.innerHTML = '';

        const response = await searchSpecies(term);

        if (response.success) {
            searchResults = response.data;
            selectedResultIndex = 0;

            displayResults(response);

            if (searchResults.length > 0) {
                // Jump to first result
                const firstResult = searchResults[0];
                world.jumpToCoordinates(firstResult.longitude, firstResult.latitude);

                // Create pins
                world.updatePins();

                // Show first result info
                displaySpeciesInfo(firstResult);
            }
        } else {
            throw new Error('Search failed');
        }
    } catch (error) {
        console.error('Failed to search species:', error);
        displayError('Failed to search species. Please try again.');
    } finally {
        // Enable searching again
        const searchButton = document.getElementById('search-button');
        searchButton.disabled = false;
        searchButton.textContent = 'Search';
    }
}

/**
 * Displays search results in a list in the left sidebar
 * @param {object} response - The response to the search query
 */
function displayResults(response) {
    const resultsList = document.getElementById('results-list');
    const resultCount = document.getElementById('result-count');

    resultCount.textContent = response.count;

    if (response.data.length === 0) {
        resultsList.innerHTML = '<div class="no-results">No results found</div>';
        return;
    }

    // Generate HTML elements for search results
    resultsList.innerHTML = response.data.map((result, index) => `
        <div class="result-item ${index === selectedResultIndex ? 'selected' : ''}" data-index="${index}">
          <div class="result-name">${result.full_scientific_name || result.unit_id}</div>
          <div class="result-location">${result.country}</div>
        </div>
      `).join('');

    // Add click handlers to result items
    resultsList.querySelectorAll('.result-item').forEach(item => {
        item.addEventListener('click', () => {
            const index = parseInt(item.dataset.index);
            selectResult(index);
        });
    });
}

/**
 * Selects a search result, jumps to the coordinates, and shows the corresponding information 
 * @param {number} index - The index of the selected search result. We treat this as the ID
 */
function selectResult(index) {
    if (index < 0 || index >= searchResults.length) return;

    selectedResultIndex = index;
    const selectedResult = searchResults[index];

    // Update UI
    document.querySelectorAll('.result-item').forEach((item, i) => {
        item.classList.toggle('selected', i === index);
    });

    currentPins.forEach((pin, i) => {
        pin.classList.toggle('selected', i === index);
    });

    // Jump to selected location
    world.jumpToCoordinates(selectedResult.longitude, selectedResult.latitude);

    // Display species info
    displaySpeciesInfo(selectedResult);
}

/**
 * Renders the details from the selected result into the species info panel
 * @param {object} result - The resulting specimen details to render
 */
function displaySpeciesInfo(result) {
    const speciesInfo = document.getElementById('species-info');

    const fields = [
        {
            label: null,
            value: result.image_url
                ? `
                    <div class="image-wrapper">
                        <div class="image-loader"></div>
                        <a data-fslightbox data-type="image" href="${result.image_url}">
                            <img 
                                src="${result.image_url}" 
                                alt="${result.full_scientific_name}" 
                                class="info-image"
                                onload="this.style.display='block'; this.closest('.image-wrapper').querySelector('.image-loader').style.display='none';"
                            >
                        </a>
                    </div>`
                : null
        },
        {
            label: 'Unit ID', value: result.unit_id
                ? `<a href="${result.unit_guid}" target="_blank" class="purl-link">${result.unit_id}</a>`
                : null
        },
        { label: 'Scientific Name', value: result.full_scientific_name },
        { label: 'Genus', value: result.genus_or_monomial },
        { label: 'Family', value: result.family },
        { label: 'Order', value: result.order_name },
        { label: 'Notes', value: result.notes },
        { label: 'Institution', value: result.source_institution_id },
        { label: 'Collection Type', value: result.collection_type },
        { label: 'Country', value: result.country },
        { label: 'Province/State', value: result.province_state },
        { label: 'Locality', value: result.locality },
        { label: 'Altitude', value: parseFloat(result.altitude) === 0 ? null : result.altitude },
        { label: 'Biotope', value: result.biotope_text },
        { label: 'Collection Date', value: new Date(result.date_time_begin).toISOString().split('T')[0] },
        { label: 'Recorded By', value: result.gathering_person_full_name },
    ];

    speciesInfo.innerHTML =
        fields
            .filter(field => field.value)
            .map(field => `
          <div class="info-field">
            ${field.label ? `<div class="info-label">${field.label}:</div>` : ''}
            <div>${field.value}</div>
        </div>
        `).join('');

    // Initialize generated elements as fslightboxes
    refreshFsLightbox(); 
}

/**
 * Renders an error message in the error container
 * @param {string} message - Error message to show
 */
function displayError(message) {
    const errorContainer = document.getElementById('error-container');
    errorContainer.innerHTML = `<div class="error-message">${message}</div>`;
}

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
    const searchButton = document.getElementById('search-button');
    const searchInput = document.getElementById('species-search');

    // Attaches a click handler to the search button to search for species
    searchButton.addEventListener('click', () => {
        const searchTerm = searchInput.value.trim();
        if (searchTerm) {
            performSpeciesSearch(searchTerm);
        }
    });

    // Enables triggering a search by pressing the 'enter' key
    searchInput.addEventListener('keypress', (event) => {
        if (event.key === 'Enter') {
            searchButton.click();
        }
    });
});
