// Textile information
const textileData = {

    pina: {

        title: "Piña",

        // Sample images
        images: [
            "../assets/images/pina.png"
        ],

        // Full description
        description:
            "Piña is a traditional Philippine textile made from pineapple leaf fibers. It is associated with the Barong Tagalog and is known for its delicate appearance, fine texture, lightweight feel, and natural sheen. Piña is commonly used for formal Filipino clothing and traditional garments.",

        // Textile details
        material:
            "Pineapple leaf fibers",

        origin:
            "The Philippines",

        uses:
            "Barong Tagalog, formal clothing, traditional garments, and other textile products",

        characteristics:
            "Delicate, lightweight, fine-textured, breathable, and naturally lustrous"

    }

};

const textileData1 = {

    jusi: {

    title: "Jusi",

    images: [
        "../assets/images/jusi.png"
    ],

    description:
        "Jusi is a traditional Philippine textile associated with formal Filipino clothing, including the Barong Tagalog. It is known for its lightweight appearance and use in formal wear.",

    material:
        "Add the verified material information here",

    origin:
        "The Philippines",

    uses:
        "Barong Tagalog and formal Filipino clothing",

    characteristics:
        "Add the verified characteristics here"
    }

};

const textileData2 = {
    "pina-seda": {

        title: "Piña-Seda",

        images: [
            "../assets/images/pina-seda.png"
        ],

        description:
            "Piña-Seda is a textile associated with Filipino formal clothing. It combines the appearance of Piña with silk-related fibers, creating a fabric used for elegant and traditional garments.",

        material:
            "Pineapple fibers and silk-related fibers. Verify the exact composition for your reference.",

        origin:
            "The Philippines",

        uses:
            "Formal clothing, Barong Tagalog, and traditional garments",

        characteristics:
            "Lightweight appearance, delicate texture, and an elegant finish"

    }
};

const textileData3 = {
    others: {

        title: "Other Textiles",

        images: [
            "../assets/images/others.jpg"
        ],

        description:
            "This category contains other textile materials that may be used in Filipino clothing and traditional garments.",

        material:
            "Varies depending on the textile",

        origin:
            "The Philippines",

        uses:
            "Clothing, formal wear, and traditional garments",

        characteristics:
            "Characteristics vary depending on the textile material"

    }

};



function openTextileModal(textileType) {

    const textile =
        textileData[textileType] ||
        textileData1[textileType] ||
        textileData2[textileType] ||
        textileData3[textileType];

    if (!textile) {
        console.log("Textile not found:", textileType);
        return;
    }

    document.getElementById("modalTitle").textContent =
        textile.title;

    document.getElementById("modalDescription").textContent =
        textile.description;

    document.getElementById("modalMaterial").textContent =
        textile.material;

    document.getElementById("modalOrigin").textContent =
        textile.origin;

    document.getElementById("modalUses").textContent =
        textile.uses;

    document.getElementById("modalCharacteristics").textContent =
        textile.characteristics;

    const modalImages =
        document.getElementById("modalImages");

    modalImages.innerHTML = "";

    textile.images.forEach(function(imagePath) {

        const image = document.createElement("img");

        image.src = imagePath;
        image.alt = textile.title + " sample";
        image.className = "modal-sample-image";

        modalImages.appendChild(image);

    });

    document.getElementById("textileModal").style.display =
        "flex";
}


// KEEP YOUR CLOSE MODAL FUNCTION BELOW

function closeTextileModal() {
    document.getElementById("textileModal").style.display =
        "none";
}