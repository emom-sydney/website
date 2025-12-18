// adapted from https://github.com/StarfallProjects/11ty-plugin-lightbox

export default function(lightbox){
    // Use thumbnail paths if available, otherwise fall back to original image paths
    const thumbPaths = lightbox.thumbPath || lightbox.imgPath;
    
    return(`
    <div class="sp-lightbox-container">
      <div class="sp-lightbox-row">
        ${thumbPaths.map((path, index) => `<div class="sp-lightbox-column">
        <img tabindex=0 class="sp-lightbox-thumbnail sp-lightbox-hover-shadow" src="${path}" onclick="openmodal();currentSlide(${index + 1})">
        <div class="sp-lightbox-caption-container sp-lightbox-thumbnail-caption">${lightbox.caption[index]}</div>
        </div>`).join('')}
      </div>
      <div id="my-sp-lightbox-modal" class="sp-lightbox-modal" onclick="closemodal()">        
        <div class="sp-lightbox-modal-content">
          ${lightbox.imgPath.map((path, index, array) => `<div class="sp-lightbox-slides"><span class="sp-lightbox-numbertext">${index + 1} / ${array.length} </span>            
          <img class="sp-lightbox-slide-img" src="${path}">
          <p class="sp-lightbox-caption-container">${lightbox.caption[index]}</p>        
          </div>`).join('')}
          <button id="sp-lightbox-prev" onclick="plusSlides(-1)">&#10094;</button>
          <button id="sp-lightbox-next" onclick="plusSlides(1)">&#10095;</button>
        </div>
        <button class="sp-lightbox-close" onclick="closemodal()">&times;</button>
      </div>
    </div>
<script>
let thumbnails = document.getElementsByClassName("sp-lightbox-thumbnail");
console.log(thumbnails);
for(let i=0; i<thumbnails.length;i++){
  thumbnails[i].addEventListener("keypress", function(event) {
    event.preventDefault();
    if(event.keyCode === 13) {
      event.target.click();
      document.getElementById("sp-lightbox-next").focus();
    }
  });  
}
function openmodal() {
   document.getElementById("my-sp-lightbox-modal").style.display = "block";
 }
function closemodal() {
  event.stopPropagation(); 
  if(event.target.className === "sp-lightbox-close" || event.target.className === "sp-lightbox-modal"){
  document.getElementById("my-sp-lightbox-modal").style.display = "none";
  }
}
var slideIndex = 1;
showSlides(slideIndex);
function plusSlides(n) {
   showSlides(slideIndex += n);
}
function currentSlide(n) {
   showSlides(slideIndex = n);
}
function showSlides(n) {
   let i;
   let slides = document.getElementsByClassName("sp-lightbox-slides");
   if (n > slides.length) {slideIndex = 1}
   if (n < 1) {slideIndex = slides.length}
   for (i = 0; i < slides.length; i++) {
       slides[i].style.display = "none";
   }
   slides[slideIndex-1].style.display = "block";
}
</script>
<style>

.sp-lightbox-caption-container {
  background-color: #FFF;
  color: #333;
  margin: 0;
  padding: 15px 0;
  font-weight: bold;
}

.sp-lightbox-thumbnail-caption {
  font-size: 0.75em;
}

.sp-lightbox-close {
  background-color: black;
  border: none;
  border-radius: 3px;
  color: white;
  cursor: pointer;
  position: absolute;
  top: 10px;
  right: 25px;
  font-size: 35px;
  font-weight: bold;
}

.sp-lightbox-close:hover,
.sp-lightbox-close:focus {
  color: #999;
  text-decoration: none;
  cursor: pointer;
}

.sp-lightbox-column {
  background-color: #FFF;  
  display: flex;
  flex-direction: column;
  height: var(--lightbox-thumbnail-height);
  justify-content: space-evenly;
  margin: 0 0.5vw 2vw 0.5vw;
  width: var(--lightbox-thumbnail-width);
  text-align: center;
}
.sp-lightbox-container {
   box-sizing: border-box;
   height: 100%;
   max-width: 100%;
}

.sp-lightbox-hover-shadow:hover {
  box-shadow: 0 4px 8px 0 rgba(0, 0, 0, 0.2), 0 6px 20px 0 rgba(0, 0, 0, 0.19);
}

.sp-lightbox-modal {
  display: none;
  position: absolute;
  z-index: 1;
  padding-top: 50px;
  left: 0;
  top: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0,0,0,1);
}

.sp-lightbox-modal-content {
  position: relative;
  margin: auto;
  padding: 0;
  max-width: 800px;
}

.sp-lightbox-numbertext {
  background-color: black;
  color: white;
  font-size: 12px;
  padding: 8px 12px;
  position: absolute;
  top: 0;
  left:0;
}

.sp-lightbox-row {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  justify-content: space-between;
}

.sp-lightbox-slide-img {
  margin-bottom: -4px;
  max-height: 600px;
  max-width:100%; 
  object-fit: cover;
}

.sp-lightbox-slides {
  background-color: black;
  display: none;
  text-align: center;
}

.sp-lightbox-thumbnail {
  cursor: pointer;
  margin-bottom: -4px;
  max-height: 85%;
  max-width: 100%;
  object-fit: cover;
}

#sp-lightbox-prev,
#sp-lightbox-next {
  background-color: black;
  border:none;
  border-radius: 0 3px 3px 0;
  color: white;
  cursor: pointer;
  font-size: 20px;
  font-weight: bold;
  margin-top: -50px;
  padding: 16px;
  position: absolute;
  top: 50%;
  transition: 0.6s ease;
  user-select: none;
  -webkit-user-select: none;
  width: auto;
 }

 #sp-lightbox-next {
   right: 0;
   border-radius: 3px 0 0 3px;
 }

 #sp-lightbox-prev:hover,
 #sp-lightbox-next:hover {
   background-color: rgba(0, 0, 0, 0.8);
}
</style>    
`);
};