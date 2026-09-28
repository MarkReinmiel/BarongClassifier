// Full-resolution phone photos exceed the ~5 MB sessionStorage limit, so the
// selected image is kept in IndexedDB and passed to the result page unchanged.
const IMAGE_DB_NAME = "barongClassifier";
const IMAGE_STORE_NAME = "images";
const IMAGE_KEY = "classifiedImage";

function openImageDb() {
    return new Promise(function (resolve, reject) {
        if (!("indexedDB" in window)) {
            reject(new Error("IndexedDB unavailable"));
            return;
        }

        const request = indexedDB.open(IMAGE_DB_NAME, 1);

        request.onupgradeneeded = function () {
            request.result.createObjectStore(IMAGE_STORE_NAME);
        };
        request.onsuccess = function () {
            resolve(request.result);
        };
        request.onerror = function () {
            reject(request.error);
        };
    });
}

function runImageTransaction(mode, action) {
    return openImageDb().then(function (db) {
        return new Promise(function (resolve, reject) {
            const transaction = db.transaction(IMAGE_STORE_NAME, mode);
            const request = action(transaction.objectStore(IMAGE_STORE_NAME));

            transaction.oncomplete = function () {
                db.close();
                resolve(request.result);
            };
            transaction.onerror = transaction.onabort = function () {
                db.close();
                reject(transaction.error);
            };
        });
    });
}

function saveClassifiedImage(dataUrl) {
    sessionStorage.removeItem(IMAGE_KEY);

    return runImageTransaction("readwrite", function (store) {
        return store.put(dataUrl, IMAGE_KEY);
    }).catch(function () {
        sessionStorage.setItem(IMAGE_KEY, dataUrl);
    });
}

function loadClassifiedImage() {
    return runImageTransaction("readonly", function (store) {
        return store.get(IMAGE_KEY);
    })
        .catch(function () {
            return null;
        })
        .then(function (dataUrl) {
            return dataUrl || sessionStorage.getItem(IMAGE_KEY);
        });
}
