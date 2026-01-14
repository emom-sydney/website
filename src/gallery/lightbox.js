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
`);
};